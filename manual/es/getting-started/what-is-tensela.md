---
title: Qué es Tensela
description: Qué hace Tensela, para quién es y qué no es.
---

Tensela es un programa de **diseño paramétrico pensado para arquitectos**.

En vez de dibujar cada pieza, describes cómo se arma el diseño: *una fachada de 20 m de ancho, partida en vanos de
1 m, con un quiebrasol en cada vano que gira hacia el sol*. Cada paso es un **nodo**, una tarjeta pequeña, y los
nodos se unen con **cables**. Cambias un número, el ancho de los vanos o el ángulo de los quiebrasoles, y todo el
diseño se actualiza frente a ti.

Funciona como una **receta**: los valores son los ingredientes, los nodos son los pasos y la forma es el plato.
Cambias un ingrediente y la misma receta te da otro plato. Eso es un algoritmo, y en Tensela lo ves en vez de
escribirlo.

## Qué puedes hacer

- **Fachadas y quiebrasoles:** paneles, quiebrasoles que abren y cierran según la distancia o el sol, pieles de
  rectángulos, hexágonos o celdas Voronoi.
- **Cubiertas y superficies:** superficies por curvas o por puntos, paraboloides hiperbólicos, costillas, mallas y
  diagrids sobre una superficie.
- **Estructuras:** cables y membranas colgantes que encuentran su forma, mallas espaciales, una primera revisión de
  barras.
- **Sol y sombra:** el sol de cualquier lugar y fecha, sombras, horas de sol en una fachada, luz natural.
- **Fabricación:** secciones y estructuras waffle, piezas acostadas en planchas con su número, un archivo listo
  para la cortadora láser, una revisión antes de imprimir en 3D.
- **Exportar:** OBJ, STL y 3MF para 3D; DXF, SVG y PDF para cortar y dibujar; PNG para imágenes.

Ocho resultados hechos con Tensela, cada uno una [receta](/es/manual/recipes/) del manual para hacerlo paso a paso:

<div class="recipe-grid compact not-content">
	<a class="recipe-card" href="/es/manual/recipes/breathing-facade/"><img src="/images/manual/recipes/breathing-facade.png" alt="" /><b>Una fachada que respira</b></a>
	<a class="recipe-card" href="/es/manual/recipes/rib-wall/"><img src="/images/manual/recipes/rib-wall.png" alt="" /><b>Un muro de costillas</b></a>
	<a class="recipe-card" href="/es/manual/recipes/waffle-model/"><img src="/images/manual/recipes/waffle-model.png" alt="" /><b>Una maqueta waffle lista para cortar</b></a>
	<a class="recipe-card" href="/es/manual/recipes/hypar-roof/"><img src="/images/manual/recipes/hypar-roof.png" alt="" /><b>Una cubierta de paraboloides</b></a>
	<a class="recipe-card" href="/es/manual/recipes/voronoi-skin/"><img src="/images/manual/recipes/voronoi-skin.png" alt="" /><b>Una piel Voronoi</b></a>
	<a class="recipe-card" href="/es/manual/recipes/twisting-tower/"><img src="/images/manual/recipes/twisting-tower.png" alt="" /><b>Una torre que gira</b></a>
	<a class="recipe-card" href="/es/manual/recipes/sun-study/"><img src="/images/manual/recipes/sun-study.png" alt="" /><b>Un estudio de sol</b></a>
	<a class="recipe-card" href="/es/manual/recipes/hanging-vault/"><img src="/images/manual/recipes/hanging-vault.png" alt="" /><b>Una bóveda que encuentra su forma</b></a>
</div>

## Qué no es Tensela

Para evitar malentendidos desde el principio:

| Tensela no es… | Porque… |
|---|---|
| **Un programa de dibujo** | Puedes dibujar curvas y puntos en la vista, pero su fuerza está en las reglas, no en trazar cada línea a mano. |
| **Un complemento (plugin)** | Funciona sola. No necesitas tener otro programa instalado. |
| **BIM** | No tiene muros, puertas ni cómputos. Hace geometría que después llevas a tu programa BIM o CAD. |
| **Un programa de render** | Para imágenes fotográficas, exporta el modelo al programa de render que ya usas. |

## Para quién es

Arquitectos y estudiantes que quieren diseñar con reglas **sin aprender a programar antes**, con una curva de
aprendizaje suave. Si ya usas una herramienta de programación visual, lee
[Si vienes de otro programa](/es/manual/getting-started/coming-from-other-programs/): casi todo lo que sabes te sigue
sirviendo.

## De dónde viene el nombre

![Tensor y tela: de dónde viene el nombre Tensela](/images/manual/diagrams/tensor-fabric-es.svg)

*Tensela* junta dos palabras. Un **tensor** es, en matemática, un bloque de números con varias direcciones: así guarda
Tensela tus listas. Una **tela** son hilos que se cruzan: cada lista es un hilo, y cada cruce es una pieza de tu
diseño. Más en [Cómo piensa Tensela](/es/manual/theory/how-tensela-thinks/).

## Cinco palabras que verás en todas partes

| Palabra | Qué significa |
|---|---|
| **Nodo** | Una tarjeta que hace una sola cosa: un rectángulo, una retícula, una distancia, un giro. |
| **Cable** | La línea que lleva lo que da un nodo hacia otro nodo. |
| **Entrada** | Un valor que necesita un nodo, como el ancho de un rectángulo. Lo escribes o lo traes por un cable. |
| **Lista** | Varios valores a la vez: 20 alturas, 300 paneles. |
| **Nivel** | El nombre de una lista: *piso*, *vano*, *panel*. Le dice a Tensela cómo combinar las listas. [Más sobre esto](/es/manual/key-ideas/named-lists/). |

## Dónde funciona y cuánto cuesta

- **Linux**, en una PC de 64 bits; alcanza una computadora modesta. Windows y macOS todavía no están disponibles.
  [Qué necesitas](/es/manual/getting-started/requirements/).
- **Gratis:** no cuesta nada y es software libre. Lo que haces con ella es tuyo.
- **Sin internet:** funciona sin conexión, sin cuenta, y Tensela nunca envía tus archivos a ningún lado.
  [Gratis, sin internet y tuyo](/es/manual/getting-started/free-offline-yours/).
