---
title: Cómo se calcula un proyecto
description: El grafo detrás del lienzo, qué se recalcula cuando cambias algo, y los límites que protegen tu trabajo.
---

Lo que pasa entre el momento en que cambias un número y el momento en que la vista 3D muestra la forma nueva. Para
quien quiera saberlo; no lo necesitas para diseñar.

## Un proyecto es un grafo

Un proyecto de Tensela es una lista de nodos, cada uno con sus entradas: un valor fijo, o una conexión a otro nodo.
El archivo `.tela` dice exactamente eso, en texto común (JSON). Este es entero [Tu primer
proyecto](/es/manual/getting-started/first-project/):

```json
{
  "nodes": {
    "facade":    {"type": "Rectangle", "width": 20, "height": 12, "plane": "elevation"},
    "panels":    {"type": "Grid", "rectangle": {"node": "facade"}, "cell_width": 1, "cell_height": 1},
    "centres":   {"type": "Centre", "geometry": {"node": "panels"}},
    "point":     {"type": "Point", "x": 6, "z": 7},
    "attractor": {"type": "Attractor", "where": {"node": "centres"}, "attractors": {"node": "point"},
                  "reach": 8, "near": 90, "far": 0},
    "fin":       {"type": "Box", "width": 0.4, "depth": 0.05, "height": 1.0},
    "fins":      {"type": "Place", "geometry": {"node": "fin"}, "at": {"node": "centres"},
                  "rotation": {"node": "attractor"}}
  }
}
```

`{"node": "facade"}` es un cable. Las clases de nodos y sus entradas se guardan siempre en inglés, así un proyecto
hecho con Tensela en español se abre igual en cualquier idioma. Como es texto, se puede leer, comparar entre dos versiones o guardar en un
sistema de control de versiones como cualquier otro archivo de texto.

![El grafo del primer proyecto](/images/manual/diagrams/first-project-graph-es.svg)

## Se calcula cuando se pide, se guarda hasta que cambia

Tensela no calcula todo el proyecto cada vez. Trabaja al revés:

1. Cuando la vista necesita el resultado de un nodo, Tensela pide primero sus entradas, y esas piden las suyas,
   hasta los valores que escribiste.
2. Cada nodo se calcula **una vez**, y guarda su resultado.
3. Cuando cambias una entrada, Tensela borra el resultado guardado de **ese nodo y de todo lo que depende de él**, y
   de nada más.

![Lo que se recalcula cuando se mueve el punto](/images/manual/diagrams/recompute-es.svg)

Así, cuando arrastras el punto del atractor, la retícula de 240 paneles no se vuelve a partir: solo se recalculan el
Punto, el Atractor y el Colocar. Por eso un proyecto grande sigue respondiendo mientras arrastras un deslizador.

```python
def change(node, input, value):
    node.inputs[input] = value
    clear(node)                       # este nodo y todo lo que viene después

def clear(node):
    node.result = None
    for after in nodes_that_use(node):
        clear(after)

def result(node):
    if node.result is None:           # no está guardado: se calcula con sus entradas
        inputs = {name: result(v) if is_node(v) else v for name, v in node.inputs.items()}
        node.result = node.kind.function(**inputs)
    return node.result
```

## Sin vueltas

Como un nodo se calcula a partir de sus entradas, un nodo no puede depender de sí mismo. Si un cable cerraría un
círculo, Tensela no lo conecta y lo dice: *Conectar «a» a «b» haría un círculo: «b» ya está antes de «a».* Para
repetir un paso sobre su propio resultado, usa un [grupo que se repite](/es/manual/key-ideas/groups/).

## La ventana sigue respondiendo

Si un cálculo tarda más de una décima de segundo, más o menos, sigue **por detrás**: la vista 3D conserva el último
resultado, aparece *Calculando… Detener*, y puedes seguir trabajando. Si cambias algo mientras tanto, ese cálculo se
descarta (ya no sirve) y empieza uno nuevo con los valores nuevos. **Detener** lo descarta y vuelve a lo que se
mostraba.

## Los errores en palabras

Cuando un nodo no puede calcular, su tarjeta dice por qué, en palabras: qué falta, qué no encaja, y casi siempre cómo
arreglarlo. El error queda en ese nodo y en los que dependen de él; el resto del proyecto sigue funcionando.

## Límites que protegen tu trabajo

- **5 millones de elementos** por resultado como máximo: por encima, un aviso antes de calcular. Casi siempre es un
  cruce de niveles que debía ir uno con uno.
- **50 000 piezas** en la vista: por encima, la vista pregunta antes de dibujar (**Mostrarlos** o **Apagar su ojo**).
- **El nodo Código** está hecho para no llegar a la red: Tensela revisa el código antes de ejecutarlo y lo detiene si
  intenta abrir archivos, conectarse o abrir otros programas. Ejecuta tu Python solo con una lista de nombres
  permitidos, y lo detiene a los 10 segundos.

## Grupos

Un grupo es un grafo dentro de un nodo. Por dentro se calcula como cualquier proyecto; por fuera es una tarjeta con
sus entradas y su salida. Un grupo que **se repite** ejecuta su grafo varias veces, devolviendo su resultado a la
entrada, una cantidad fija de veces.
