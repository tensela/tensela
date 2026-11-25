---
title: Las listas con nombre, por dentro
description: Cómo se guarda una lista con niveles, la única regla que las combina, y cómo se ve en código.
---

Esta página es para quien quiere saber cómo funcionan por dentro las [listas con
nombre](/es/manual/key-ideas/named-lists/), con algo de código. No la necesitas para diseñar. El código es Python,
simplificado del código fuente de Tensela (el archivo `data.py`); los nombres van en inglés, como en el programa.

## Qué es un valor

Cada valor de Tensela, desde un solo número hasta las esquinas de mil paneles, es un **Data**: un bloque de números
(un arreglo de *numpy*) y los nombres de sus primeras direcciones, sus **niveles**.

![Un bloque de números con direcciones con nombre](/images/manual/diagrams/block-es.svg)

```python
centres = Data(values,                    # un arreglo de numpy de 12 × 20 × 3
               levels=("row", "column"),  # los nombres de las dos primeras direcciones
               name="centres")

centres.sizes   # {"row": 12, "column": 20}
centres.shape   # "row 12 × column 20 = 240"   (lo que dice el cable)
```

Las direcciones después de los niveles describen **cada elemento**: un número no tiene ninguna, un punto tiene una
de tamaño 3 (x y z), un rectángulo tiene sus cuatro esquinas. Así, el bloque de 240 centros es de 12 × 20 × 3, pero
solo *fila* y *columna* son listas.

## La única regla

Todo nodo que combina entradas pasa por la misma función, `align`. Tiene tres pasos:

1. **El resultado tiene todos los niveles de las entradas**, en el orden en que aparecen.
2. **Un nivel que está en dos entradas tiene que tener el mismo tamaño en las dos**; va uno con uno. Si los tamaños
   no coinciden, Tensela se detiene con un aviso en vez de adivinar.
3. **Un nivel que está en una sola entrada se cruza** con todos los demás.

```python
def align(*inputs):
    levels, sizes = [], {}
    for data in inputs:
        for level, size in data.sizes.items():
            if level not in sizes:              # un nivel nuevo: entra en el resultado
                levels.append(level)
                sizes[level] = size
            elif sizes[level] != size:          # el mismo nombre, otro tamaño: un aviso claro
                raise ShapeError(f"No coinciden los tamaños de «{level}»: …")
    return levels, [extend(d, levels, sizes) for d in inputs]
```

`extend` lleva cada bloque a todas las direcciones del resultado. Lo gira al orden del resultado, le da tamaño 1 en
los niveles que no tiene y lo **estira** hasta el tamaño completo. El estirado es el *broadcasting* de numpy: no se
copia ningún número, el bloque solo se lee como si fuera más grande.

![Los tres pasos de la regla](/images/manual/diagrams/align-es.svg)

```python
def extend(data, levels, sizes):
    order = sorted(range(len(data.levels)), key=lambda axis: levels.index(data.levels[axis]))
    block = numpy.transpose(data.values, order + element_axes)
    block = block.reshape([data.sizes.get(n, 1) for n in levels] + element_shape)
    return numpy.broadcast_to(block, [sizes[n] for n in levels] + element_shape)
```

Con las entradas alineadas, un nodo se escribe **una vez, para bloques enteros**, y funciona igual para un elemento
que para 24 000:

```python
>>> heights = Data([0, 3.5, 7, 10.5], levels=("piso",), name="alturas")
>>> x = Data([0, 1, 2, 3, 4], levels=("vano",), name="x")
>>> points = apply(make_point, x, heights)        # nombres distintos: se cruzan
>>> points.shape
'piso 4 × vano 5 = 20'
>>> shift = Data([0, 0.2, 0.4, 0.6], levels=("piso",), name="desplazamiento")
>>> apply(add, heights, shift).shape              # el mismo nombre: uno con uno
'piso 4'
>>> apply(add, heights, Data(range(5), levels=("piso",), name="cinco"))
ShapeError: No coinciden los tamaños de «piso»: 4 en «alturas», 5 en «cinco».
```

## Trabajar sobre un nivel, por su nombre

Como los niveles tienen nombre, una operación puede decir **sobre cuál** trabaja sin contar posiciones:

```python
reduce(areas, "sum", along="panel")      # el área de cada piso: se suman los paneles
reorder(points, "piso", mode="invert")   # los pisos al revés; los vanos como estaban
```

**Resumir**, **Reordenar**, **Filtrar**, **Elegir** y **Partir** piden un nivel por su nombre. No hay *transponer*:
`piso × vano` y `vano × piso` son el mismo bloque, porque el orden de los niveles nunca decide nada.

## Listas que no son rectangulares

Los proyectos reales no siempre son bloques regulares:

- **Niveles de tamaño variable.** Una torre con más paneles abajo que arriba: el nivel *panel* tiene un tamaño
  distinto en cada piso. Tensela guarda el bloque completado hasta el tamaño mayor, la **cuenta** de paneles de cada
  piso y una **máscara** que dice qué celdas existen de verdad. Los nodos solo leen las celdas que existen.
- **Huecos.** De fábrica, **Filtrar** no quita elementos: los deja **vacíos en su lugar**, así la retícula se sigue
  leyendo igual (el panel de la fila 3, columna 7 sigue ahí, o es un lugar vacío). Con *quitar: sí*, los que quedan
  se numeran de nuevo.
- **Numeración.** Los elementos de un nivel se numeran desde 0, salvo que el nivel empiece en otro número: con dos
  subsuelos, los pisos van desde −2.

## Una red de seguridad

Antes de calcular, `align` multiplica los tamaños del resultado. Por encima de **5 millones de elementos** se
detiene con un aviso en vez de congelar la computadora: casi siempre son dos niveles que se cruzan y deberían ir uno
con uno (el mismo nombre), o un dígito de más.

## Por qué «tensor»

Un bloque de números con varias direcciones es lo que la matemática llama **tensor**. La mayoría de los programas
numeran sus direcciones (eje 0, eje 1, eje 2). Tensela les pone nombre. Ese cambio pequeño es lo que quita la
necesidad de acomodar los datos a mano, y de ahí viene el nombre *Tensela*: [Cómo piensa
Tensela](/es/manual/theory/how-tensela-thinks/).
