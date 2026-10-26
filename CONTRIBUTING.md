# Contribución

## Flujo de trabajo

1. Revisar `git status` y conservar cualquier cambio pendiente.
2. Sincronizar `main` con `git fetch origin` y `git pull --ff-only`.
3. Mantener cada cambio dentro de la etapa de desarrollo correspondiente.
4. Ejecutar formato, análisis, pruebas y comprobaciones indicadas en el README.
5. Preparar rutas concretas y revisar `git diff --cached` antes de cada commit.
6. Publicar en `main` y comprobar el commit remoto y los resultados de integración continua.

## Commits

Formato Conventional Commits: `tipo(alcance): descripción`.

| Tipo | Propósito |
| --- | --- |
| `feat` | Funcionalidad nueva. |
| `fix` | Corrección de un defecto. |
| `chore` | Estructura, dependencias y mantenimiento. |
| `docs` | Documentación. |
| `test` | Pruebas. |
| `refactor` | Reorganización sin cambiar el comportamiento. |
| `ci` | Integración continua. |

Usar ámbitos como `api`, `web`, `schemas` o `db` cuando aporten contexto. Cada clase se entrega mediante un único commit que reúne sus cambios completos y coherentes. No reescribir el historial publicado ni forzar subidas sin autorización expresa.

## Código y datos

- Código Python con cuatro espacios y formato Ruff.
- Nombres de módulos y campos en inglés, en `snake_case`; clases en `PascalCase`.
- Dependencias de ejecución separadas por aplicación; herramientas de calidad en `requirements-dev.txt`.
- Credenciales únicamente en el entorno o en archivos `.env` excluidos de Git.
- Datos ficticios y conexiones simuladas en pruebas automáticas.
- Comprobaciones contra Atlas explícitas y fuera de las pruebas automáticas.
- No versionar entornos virtuales, bases locales, cachés ni información personal.
