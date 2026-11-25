---
title: Qué necesitas
description: La computadora, el sistema, la memoria y los gráficos que necesita Tensela, medidos en una máquina real.
---

:::note
La primera versión de Tensela está en camino. Las cifras de esta página se midieron con la versión en desarrollo; el
tamaño exacto del archivo estará en la página de [Descarga](/es/download/).
:::

## En resumen

![Lo que necesita Tensela, de un vistazo](/images/manual/sketches/specs-es.svg)

| | Alcanza | Mejor |
|---|---|---|
| **Sistema** | Linux, de 64 bits, en una PC (x86-64): Ubuntu 22.04, Debian 12, Fedora 35, Linux Mint 21 o más nuevo | la última versión de tu distribución |
| **Procesador** | 2 núcleos | 4 núcleos o más |
| **Memoria (RAM)** | 4 GB | 8 GB o más |
| **Gráficos** | OpenGL 3.2: alcanzan los gráficos integrados en el procesador | cualquier tarjeta gráfica |
| **Disco** | 1 GB libre | |
| **Pantalla** | 1366 × 768 | 1920 × 1080 o más |
| **Ratón** | con rueda | de tres botones (una rueda que se puede apretar) |
| **Internet** | no hace falta | |

## Medido en una computadora modesta

Tensela se desarrolló y se probó todos los días en una computadora modesta, a propósito: una computadora de
escritorio pequeña, con un procesador Intel de 4 núcleos de la familia N100, los gráficos integrados en el procesador y
**sin tarjeta gráfica**.

![La computadora modesta en la que se hizo Tensela](/images/manual/sketches/mini-pc-es.svg)

> Si funciona bien aquí, lo normal es que funcione bien en una computadora común que cumpla lo de arriba.

Lo que usó en esa computadora:

| | Memoria | Tiempo |
|---|---|---|
| La ventana abierta, vacía | unos 450 MB | abre en pocos segundos |
| La ventana con un proyecto, desde el primer proyecto hasta los ejemplos más grandes | de 450 a 520 MB | |
| Los cálculos más pesados de los ejemplos (la optimización topológica de un puente o de un árbol) | menos de 200 MB más | de 4 a 7 segundos |

O sea, una computadora con 4 GB de memoria alcanza para Tensela y el sistema; con 8 GB puedes tener un navegador y
otros programas abiertos al lado.

## El sistema

- **Linux en una PC (x86-64).** Tensela necesita las bibliotecas del sistema de Ubuntu 22.04, Debian 12, Fedora 35,
  Linux Mint 21 o cualquier distribución más nueva (glibc 2.34). Las computadoras con procesador Arm (una Raspberry
  Pi, una Mac con procesador de Apple) todavía no.
- **Wayland y X11** funcionan los dos. En GNOME con Wayland, Tensela pasa por X11, para que sus paneles se puedan
  sacar de la ventana; las bibliotecas pequeñas que necesita para eso vienen dentro de Tensela.
- **En una máquina virtual**, activa su aceleración 3D.
- **Windows y macOS: todavía no.** Tensela nació para Linux; las versiones para Windows y macOS vendrán cuando haya
  recursos para hacerlas bien ([quién hace Tensela](/es/manual/getting-started/who-makes-tensela/)).

## Los gráficos

La vista 3D necesita **OpenGL 3.2 o más nuevo**, que tienen casi todos los gráficos de los últimos diez años,
también los integrados en el procesador. Para revisar los tuyos, en una terminal: `glxinfo -B` y mira *OpenGL core
profile version* (en Ubuntu y Debian `glxinfo` viene en el paquete `mesa-utils`). Alcanzan los controladores que
trae tu distribución.

## Internet

Tensela no necesita internet para funcionar: todo pasa en tu computadora. Más en
[Gratis, sin internet y tuyo](/es/manual/getting-started/free-offline-yours/).
