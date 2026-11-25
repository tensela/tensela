---
title: Tropiezos frecuentes
description: Lo que suele fallar al principio, y cómo arreglarlo.
---

Cosas que confundieron a quienes probaron Tensela mientras se hacía, para que no tengas que descubrirlas tú.

## Al instalar y abrir

- **No abre con doble clic.** Primero revisa que se pueda ejecutar (el paso 2 de
  [Instalar](/es/manual/getting-started/install/)). Después ábrela desde una terminal, `./Tensela-*.AppImage`, para
  leer qué dice. Si habla de **FUSE**, a tu sistema le falta una biblioteca que usan las AppImage: instálala (en
  Ubuntu 24.04 o más nuevo `sudo apt install libfuse2t64`, antes `libfuse2`), o abre Tensela sin ella con
  `./Tensela-*.AppImage --appimage-extract-and-run`.
- **La vista 3D queda negra, o la ventana se cierra al abrir.** Son los gráficos: Tensela necesita OpenGL 3.2 o más
  nuevo (mira [Qué necesitas](/es/manual/getting-started/requirements/#los-gráficos)). Actualiza tu sistema; en una
  máquina virtual, activa su aceleración 3D.
- **El programa está en otro idioma.** **Preferencias → General → Idioma**; se aplica la próxima vez que abras
  Tensela.

## Escribir números

- **Decimales:** valen `3,5` y `3.5`.
- **Varios valores:** siempre separados por punto y coma, `1,5; 2; 3`. Con decimales, `0,0,1,5` no se puede leer:
  escribe `0; 0; 1,5` o `0 0 1.5`.
- **Un punto:** `0 0 0`, `8 0 2,5` o `(0; 0; 1,5)`.
- **Unidades:** las medidas van en metros, salvo que lo cambies en **Preferencias → Unidades**. También puedes
  escribir la unidad con el número, `120 cm`, y Tensela la convierte.

## En la tarjeta

- **Tab** pasa al valor siguiente de la tarjeta.
- **Supr** dentro de un campo borra letras, no el nodo.
- **Un nivel vacío** en Reordenar, Filtrar o Partir quiere decir *automático*: la tarjeta dice qué nivel tomó, por
  ejemplo `auto: punto`.

## Situaciones comunes

- **Subir un punto sin escribir coordenadas:** usa **Mover** con una distancia (sube de fábrica), o **Línea por
  dirección**.
- **Después de Filtrar**, con **quitar: sí** los elementos que quedan se numeran de nuevo desde 0. Con **no**, los
  otros quedan en su lugar, vacíos.
- **Una curva con puntos vacíos** pasa por los puntos que hay.
- **Un rectángulo no es un cuerpo cerrado**, así que no tiene volumen. Para medir un volumen, extrúyelo con tapas
  primero.
- **Relieves sin fórmulas:** una curva guía, una **Distancia** hasta ella y una **Gráfica** para dar forma a la
  respuesta.
- **Una superficie suave con escalones:** una superficie suave por una retícula gruesa de puntos muestra pequeños
  escalones en las aristas vivas. Usa más puntos, o apaga **suave** en formas con aristas.

## Cuando va lento

- **Apaga los ojos** de los nodos que no necesitas ver: dibujar miles de piezas suele tardar más que calcularlas.
- **Prueba ideas con cantidades pequeñas** (menos paneles, menos secciones) y súbelas al final.
- **Los nodos pesados** (Optimización topológica, Equilibrio, Asoleamiento) tardan más cuanto más fino trabajan:
  baja la resolución, los tramos o la cantidad de paneles que les das mientras buscas la forma.

## Cuando la vista pregunta antes de dibujar

Si un nodo con el ojo encendido da más de 50 000 piezas (o 2 millones de puntos), arriba de la vista aparece una
franja: **Mostrarlos** o **Apagar su ojo**. Casi siempre es un dígito de más en una cantidad, o dos listas que se
cruzan sin querer. Revisa los nombres de sus niveles.
