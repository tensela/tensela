---
title: Mallas
description: Geometría y topología, el frente de una cara, paneles planos, y formas suaves a partir de jaulas gruesas.
---

## NURBS o malla

Una **NURBS** es una sola entidad suave definida por una fórmula. Una **malla** es un conjunto de caras planas unidas
por sus esquinas: no es suave, solo se ve más suave cuantas más caras tiene. Para formas libres difíciles de
describir (una mesa, un objeto), una malla suavizada por subdivisión es más cómoda que una NURBS.

## Geometría y topología

Una malla tiene **vértices**, que son su **geometría** (dónde están las cosas), y **caras**, que son su
**topología** (cómo se unen). Los mismos puntos unidos de otra forma son otra malla; las mismas caras con un punto
movido son otra geometría con la misma topología.

## El frente de una cara

El orden de las esquinas de una cara dice cuál es su frente: contra reloj visto desde el frente. Dos caras vecinas
son **compatibles** cuando recorren su arista común en sentidos opuestos; una malla con todas sus caras compatibles
es **orientable**. **Caras de malla** con *orientación* dice +1 o −1 para cada cara.

## Paneles planos

Los triángulos siempre son planos; un cuadrilátero puede no serlo. Para la arquitectura libre construida con vidrio
o tablero plano, lo que importa es una malla de **cuadriláteros planos**. Una superficie de revolución o de traslación
(una curva que recorre otra) los da; una forma libre no, y entonces **Planarizar** deja planos los paneles, o
**Triangular** los parte en triángulos a cambio de más juntas.

## Subdivisión

**Suavizar malla** parte cada cara y mueve los vértices hacia la superficie suave que la malla representa, nivel tras
nivel. Modela una jaula gruesa con pocas caras, mueve sus esquinas a mano con **Editar malla**, y deja que los niveles
la redondeen.
