---
title: La vista 3D
description: Moverse, mirar desde un lado, los estilos de la vista, y ver o apagar lo que hace cada nodo.
---

## Moverse

La vista siempre gira alrededor de lo que está bajo el puntero, con la vertical siempre vertical. La rueda acerca
hacia el puntero (o hacia el centro, en Preferencias).

| Esquema | Girar | Desplazar | Acercar |
|---|---|---|---|
| **Tensela** (de fábrica) | botón izquierdo | Mayús + izquierdo, o el del medio | derecho, o la rueda |
| **Blender** | el del medio | Mayús + medio | Ctrl + medio, o la rueda |
| **Rhino** | derecho | Mayús + derecho | Ctrl + derecho, o la rueda |
| **SketchUp** | el del medio | Mayús + medio | la rueda |

Elige el esquema al que estás acostumbrado en **Preferencias → Interacción → Ratón en la vista 3D**.

## Mirar desde un lado

- El menú **Vistas** de la vista: frente, lados, arriba, abajo, o isométrica. El teclado numérico hace lo mismo.
- La tecla **5** cambia entre **perspectiva** y **paralela**, como un dibujo técnico.
- **F** encuadra todo.

## Estilos

![Seis de los siete estilos de la vista 3D sobre la misma cubierta](/images/manual/app/view-styles-es.png)

| Estilo | Qué muestra |
|---|---|
| **Estudio** | cada objeto con su color, con luz suave, rincones más oscuros y contornos finos |
| **Maqueta** | todo blanco con contornos, como una maqueta de cartón pluma |
| **Matcap** | cada cara con la luz de un material (yeso, arcilla, grafito, cerámica): las piezas juntas se leen una por una |
| **Alambre** | solo las aristas |
| **Líneas ocultas** | como un dibujo de líneas: lo de atrás queda oculto |
| **Rayos X** | todo semitransparente |
| **Oclusión ambiental** | sólido, con rincones y encuentros más oscuros, como un día nublado |

El estilo se cambia en la cabecera de la vista o con un clic derecho sobre ella.

## Lo que se ve

Cada nodo que hace geometría tiene un **ojo** en su tarjeta: encendido, se ve y se exporta.

| Teclas | Qué hacen |
|---|---|
| **H** | apagar los elegidos |
| **Mayús + H** | ver solo los elegidos |
| **Alt + H** | ver todos |
| **Alt + Mayús + H** | apagar todos |
| **/** | aislar el nodo elegido, encuadrado; otra vez para volver |

## Color y números

En el panel Nodo, cada geometría tiene su **color** y su **opacidad**, o se pinta **según un valor** (el área de cada
panel, el sol que recibe) con una leyenda; **Ver → Leyendas de colores** las muestra en la vista, para una captura.
**Numerar en 3D** escribe el número de cada elemento, y **Ver el sentido** dibuja hacia dónde van las curvas.
