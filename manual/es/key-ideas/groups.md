---
title: Grupos
description: Guardar varios nodos en una sola tarjeta, usarla muchas veces, y repetir un paso.
---

## Para qué

- **Ordenar:** una cadena larga se vuelve una tarjeta con un nombre claro, como un capítulo.
- **Hacer tu propio nodo:** un grupo es una **nueva clase de nodo**, un *quiebrasol* o un *panel con marco*, que
  puedes usar todas las veces que quieras.
- **Repetir un paso:** un paso cuyo resultado vuelve a entrar, varias veces (un fractal, una curva que se subdivide).

## Cómo

1. Elige los nodos, arrastrando un recuadro o con Ctrl + clic, y pulsa **Ctrl + G**.
2. Ponle un nombre al grupo: ese nombre es la **nueva clase de nodo**.
3. **Doble clic** en la tarjeta del grupo para entrar; **Salir del grupo** sube de nuevo. **Desagrupar**
   (Ctrl + Mayús + G) deja los nodos sueltos otra vez.

## Qué hace

![Por dentro, varios nodos; por fuera, una sola tarjeta](/images/manual/diagrams/groups-es.svg)

- **Lo que entra:** los cables que llegaban a los nodos desde afuera se vuelven las entradas del grupo.
- **Lo que sale:** la tarjeta del grupo da un resultado. Si dos de los nodos se usan afuera, aparece al lado una
  tarjeta **Resultado de grupo** con el nombre del nodo que reemplaza. El grupo se calcula una sola vez para los dos.
- **Lo cambias una vez, cambia en todas partes:** lo que cambies dentro de un grupo vale para todos los nodos de esa
  clase.
- **Grupos dentro de grupos:** dentro de un grupo puedes agrupar, separar y entrar en otro grupo, tan hondo como
  quieras.
- **Ojos adentro:** dentro de un grupo, encender el ojo de un nodo muestra lo que calcula con lo que llega a esa
  tarjeta; lo de afuera queda tenue.

## Repetir

Un grupo se puede **repetir**: escribe **repetir** `3` en su tarjeta. La primera vez recibe lo que tiene conectado;
después, su propio resultado.

- **vuelve por:** por qué entrada vuelve a entrar el resultado (vacío: la primera). Las demás entradas reciben lo
  mismo en cada paso.
- **conservar:** solo el último paso, o todos los pasos a lo largo de un nivel nuevo, *paso*, con el inicio primero
  (paso 0).
- Una entrada del grupo que se llame `paso` recibe el número de cada paso: 0, 1, 2…

**Truco:** lo que sale tiene que poder entrar por donde entró el inicio: una línea por una línea. Si no, un aviso dice
en qué paso falló.
