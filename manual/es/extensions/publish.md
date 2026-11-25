---
title: Publicar una extensión
description: Ponerla en la página Extensiones de tensela.com, actualizarla y comprobar el .zip que bajas.
---

## Para qué

Para que cualquiera la encuentre en la [página Extensiones](/es/extensions/) de tensela.com, con su ficha, lo que
puede hacer, su `.zip` y su huella.

## Cómo

1. **Su código, en un repositorio público.** El catálogo lo pide: cualquiera puede leer qué hace.
2. **Una publicación (release) con su `.zip`.** Con la plantilla, marca la versión (`git tag v0.1.0`,
   `git push --tags`): su flujo corre las pruebas, la empaqueta y adjunta el `.zip` y `SHA256SUMS`.
3. **Su archivo para el catálogo**, hecho a partir del `.zip` con la herramienta del repositorio
   [tensela-extensions](https://github.com/tensela/tensela-extensions):

   ```bash
   python tools/catalogue.py entry facade-tools-0.1.0.zip https://github.com/…/facade-tools-0.1.0.zip > extensions/facade-tools.json
   ```

   Copia lo que dice su ficha y calcula su huella. Léelo: es lo que muestra la página.
4. **Un pull request** con ese archivo. Una revisión automática corre sola (el `.zip` es el que dice su huella, y su
   ficha coincide con su archivo), y después lo revisa una persona.

## Qué se revisa

- Su código es público, y el `.zip` tiene lo que dice ese código.
- Sus permisos tienen sentido para lo que hace, y cada uno dice para qué.
- Nada escondido: nada de código que se baja mientras corre, ningún dato de la persona enviado a ningún lado sin
  decirlo, nada ofuscado.
- Su ficha está completa: nombre, qué hace, quién la hace, licencia, código, dónde reportar un problema.

Los problemas de una extensión se reportan donde dice su ficha, a quien la hace.

## Actualizarla

Cambia `version` en su ficha, marca la publicación nueva, y un pull request que cambie `version`, `download`,
`sha256` y `updated` en su archivo. Quien instale el `.zip` nuevo ve «Actualiza la instalada».

## Comprobar un .zip que bajaste

Su página en tensela.com dice su huella (SHA-256). En una terminal:

```bash
sha256sum facade-tools-0.1.0.zip
```

Si los 64 caracteres son iguales, el `.zip` es el que se revisó.
