---
title: Curvatura y superficies desarrollables
description: ¿Se puede hacer con chapa plana, o hay que moldearla? La curvatura gaussiana y la media.
---

## La pregunta del constructor

Antes que nada, un constructor le pregunta a una superficie curva: **¿se puede hacer con chapa plana** (metal,
contrachapado (terciado), cartón) **o hay que moldearla?** La curvatura lo responde.

## Curvatura gaussiana

- **Cero:** se puede hacer con chapa plana sin estirarla. Planos, cilindros, conos.
- **Positiva:** se curva hacia el mismo lado en todas las direcciones, como una cúpula. Hay que moldearla o cortarla
  en gajos.
- **Negativa:** se curva hacia lados opuestos, como una silla de montar. También hay que moldearla.

## Curvatura media

Cuánto se **dobla** la superficie en promedio. Una silla equilibrada tiene curvatura media cero y aun así no se puede
hacer con chapa plana: por eso hacen falta las dos. El signo de la media depende de hacia dónde mira la cara; para un
patrón, usa su valor absoluto (`abs` en una Fórmula).

## Superficies desarrollables

Una superficie que sale de doblar una hoja sin estirarla es **desarrollable**: su curvatura gaussiana es cero en
todas partes. **Curvatura de superficie** responde sí o no, y **Desarrollar** la estira sobre el plano de forma
exacta.

Una superficie que no es desarrollable, como una cúpula, igual se puede construir con piezas planas: córtala en gajos
con **Parte de superficie** y desarrolla cada uno. **Desarrollar** dice cuánto se estira cada pieza; con más gajos,
cada uno se estira menos.
