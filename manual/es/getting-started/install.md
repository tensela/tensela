---
title: Instalar
description: Cómo descargar y abrir Tensela en Linux.
---

:::note
La primera versión de Tensela está en camino. Estos son los pasos que tendrá.
:::

Tensela viene en un solo archivo, una **AppImage**: por lo general, nada que instalar y nada que configurar.
También hay una [carpeta portátil](#la-carpeta-portátil). Antes de empezar, mira
[Qué necesitas](/es/manual/getting-started/requirements/): alcanza una PC con Linux de 64 bits y 4 GB de memoria.

1. **Descarga** el archivo `Tensela-….AppImage` desde la página [Descargar](/es/download/).
2. **Permite que se ejecute:** clic derecho sobre el archivo, abre **Propiedades** y activa **Permitir ejecutar el
   archivo como un programa**. Desde una terminal: `chmod +x Tensela-*.AppImage`.
3. **Ábrelo** con doble clic. La primera vez, Tensela ofrece agregarse al **menú de aplicaciones** de tu escritorio,
   con su icono, y que los `.tela` se abran con doble clic. Si dices que no, está en **Preferencias → General → Menú
   de aplicaciones**.

## La carpeta portátil

Para quien no puede usar una AppImage, o la quiere en `/opt`: la misma Tensela como carpeta, en
`Tensela-….tar.gz`.

1. **Descomprímela** donde quieras (clic derecho → Extraer aquí, o `tar -xzf Tensela-*.tar.gz`).
2. **Ábrela** con `./tensela`, dentro de la carpeta.
3. Para tenerla en el menú: **Preferencias → General → Menú de aplicaciones**.

## Comprobar la descarga

La página [Descargar](/es/download/) dice la **huella** (SHA-256) de cada archivo, y ofrece el archivo
`SHA256SUMS`. Con los dos en la misma carpeta, en una terminal:

```bash
sha256sum -c SHA256SUMS --ignore-missing
```

Si dice **OK**, el archivo es el que se publicó.

Las huellas dicen que el archivo llegó entero. Para saber **quién las publicó**, `SHA256SUMS` viene con una firma,
`SHA256SUMS.minisig`, hecha con una clave que solo tiene Tensela. Compruébala con minisign
(`sudo apt install minisign`), con los dos archivos en la misma carpeta. La página Descargar tiene el comando con la
clave pública ya puesta, listo para copiar:

```bash
minisign -Vm SHA256SUMS -P <la clave pública de Tensela>
```

Si dice **Signature and comment signature verified**, las huellas son las que publicó Tensela. La misma clave
pública está en el repositorio, en `tensela.pub`.

## Tus archivos

- Tus proyectos terminan en `.tela`. Ábrelos desde **Archivo → Abrir**, o con doble clic cuando Tensela esté en tu
  menú.
- Lo que diseñas con Tensela es tuyo: la licencia del programa (GPL-3.0, software libre) cubre el programa, no tus
  proyectos. Explicado en palabras simples en [Gratis, sin internet y
  tuyo](/es/manual/getting-started/free-offline-yours/).

## Si no abre

Mira [Tropiezos frecuentes → Al instalar y abrir](/es/manual/common-stumbles/#al-instalar-y-abrir).
