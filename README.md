# Techgear_Shop

Taller 2 de APIs: tienda de hardware y accesorios tecnológicos con FastAPI, Django MVT y MongoDB Atlas.

## Estructura

- `techgear_api/app/main.py`: aplicación FastAPI, ciclo de vida de MongoDB y rutas documentadas en Swagger.
- `techgear_api/app/api/`: autenticación, usuarios, productos, pedidos y conversión de respuestas.
- `techgear_api/app/core/`: configuración validada, hash de contraseñas y tokens.
- `techgear_api/app/db/`: conexión a MongoDB y creación explícita de colecciones e índices.
- `techgear_api/app/schemas/`: contratos Pydantic para datos recibidos y respuestas.
- `techgear_api/tests/`: pruebas con información ficticia y conexiones simuladas.
- `techgear_web/config/`: estructura inicial de Django MVT, que consumirá la API por HTTP.
- `pyproject.toml`: reglas de formato y análisis estático con Ruff.

## Alcance funcional

- Cuentas de clientes guardadas en MongoDB. Registro público asigna rol de cliente; un administrador puede registrar clientes.
- Contraseñas almacenadas como hash Argon2. El inicio de sesión emite tokens Bearer de duración limitada.
- CRUD administrativo de productos. Las consultas públicas muestran solo productos activos; el borrado es lógico para conservar pedidos históricos.
- Creación de pedidos autenticados: el servidor determina cliente y precios, conserva copia del SKU, nombre y precio, calcula subtotales con `Decimal` y descuenta stock.
- Las existencias se descuentan al confirmar el pedido, no al cambiar el carrito. Si una compra falla por disponibilidad, la transacción no guarda pedido ni descuentos parciales.
- Los administradores pueden avanzar estados secuenciales. Cancelar un pedido confirmado o en preparación devuelve las existencias; después de enviado no se puede cancelar.
- No se integran pagos, transportadoras ni otros terceros.

El catálogo comienza vacío: no se cargan datos de productos sin verificar las especificaciones y precios en fuentes del fabricante o del vendedor autorizado.

## Requisitos e instalación

Se requiere Python 3.14 y acceso a MongoDB Atlas. Desde la raíz del repositorio, crea los entornos independientes:

```powershell
python -m venv techgear_api/.venv
& ./techgear_api/.venv/Scripts/python.exe -m pip install -r techgear_api/requirements.txt
python -m venv techgear_web/.venv
& ./techgear_web/.venv/Scripts/python.exe -m pip install -r techgear_web/requirements.txt
```

Si no existen, copia los archivos de ejemplo sin reemplazar configuraciones locales:

```powershell
if (-not (Test-Path ./techgear_api/.env)) { Copy-Item ./techgear_api/.env.example ./techgear_api/.env }
if (-not (Test-Path ./techgear_web/.env)) { Copy-Item ./techgear_web/.env.example ./techgear_web/.env }
```

Completa `techgear_api/.env` con la URI privada del clúster, la base `techgear_shop` y una clave aleatoria `JWT_SECRET_KEY` de al menos 32 bytes. En `techgear_web/.env`, configura la clave de Django y la URL de API. Los archivos `.env` están excluidos de Git.

| Variable | Aplicación | Uso |
| --- | --- | --- |
| `MONGO_URI` | API y Web | URI privada de MongoDB Atlas. |
| `MONGO_DB_NAME` | API | Base del proyecto: `techgear_shop`. |
| `JWT_SECRET_KEY` | API | Clave de firma privada de los tokens, mínimo 32 bytes. |
| `JWT_ACCESS_TOKEN_MINUTES` | API | Duración del token; por defecto 30 minutos. |
| `DJANGO_SECRET_KEY` | Web | Clave privada de Django, generada localmente. |
| `DJANGO_DEBUG` | Web | `True` para desarrollo local; `False` fuera de ese entorno. |
| `DJANGO_ALLOWED_HOSTS` | Web | Hosts permitidos separados por comas. |
| `TECHGEAR_API_URL` | Web | Dirección de API; localmente `http://127.0.0.1:8001`. |

Para generar una clave local de JWT sin imprimirla en el código fuente, puedes usar:

```powershell
& ./techgear_api/.venv/Scripts/python.exe -c "import secrets; print(secrets.token_hex(32))"
```

Guarda el resultado solo en `.env` o en el gestor de variables de Render.

## Preparación de MongoDB y primer administrador

Desde `techgear_api`, prepara las colecciones e índices necesarios. El comando es explícito e idempotente; no inserta productos ni cuentas:

```powershell
& ./.venv/Scripts/python.exe -m app.db.mongodb --initialize
```

Crea manualmente el primer administrador con solicitud interactiva y contraseña oculta:

```powershell
& ./.venv/Scripts/python.exe -m app.cli create-admin
```

Este comando crea una cuenta en la base configurada. No se ejecuta automáticamente al arrancar la aplicación.

## Ejecución local y Swagger

Desde la raíz, inicia FastAPI:

```powershell
& ./techgear_api/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir techgear_api --host 127.0.0.1 --port 8001 --reload
```

La API está en <http://127.0.0.1:8001/> y la documentación interactiva en <http://127.0.0.1:8001/docs>. Para Django, en otra terminal:

```powershell
& ./techgear_web/.venv/Scripts/python.exe techgear_web/manage.py runserver 127.0.0.1:8000
```

En Swagger, prueba primero `POST /auth/register` para crear un cliente, luego inicia sesión en `POST /auth/login` y copia `access_token` en **Authorize**. Las rutas marcadas con candado aceptan ese token. El administrador se crea con el comando anterior; desde su token puede registrar clientes y administrar productos y pedidos.

### Rutas principales

| Método y ruta | Acceso | Operación |
| --- | --- | --- |
| `POST /auth/register` | Público | Registro de cliente. |
| `POST /auth/login` | Público | Inicio de sesión y entrega de token. |
| `GET /users/me` | Cliente o administrador | Perfil autenticado. |
| `POST /users/` | Administrador | Registro administrativo de cliente. |
| `GET /products/`, `GET /products/{id}` | Público | Catálogo y consulta de producto activo. |
| `POST /products/`, `PUT /products/{id}`, `DELETE /products/{id}` | Administrador | Crear, editar y desactivar productos. |
| `POST /orders/` | Cliente o administrador | Confirmar pedido y descontar inventario. |
| `GET /orders/`, `GET /orders/{id}` | Autenticado | Ver pedidos propios; administradores ven todos. |
| `PATCH /orders/{id}/status` | Administrador | Avanzar estado o cancelar antes del envío. |

Los estados permitidos avanzan así: `confirmed` → `preparing` → `shipped` → `delivered`. Desde `confirmed` y `preparing` también se permite `cancelled`; desde `shipped` solo se permite `delivered`.

## Despliegue de la API en Render

El servicio se configura directamente en el panel de Render. Usa la raíz `techgear_api`, el comando de compilación `pip install -r requirements.txt`, el comando de inicio `uvicorn app.main:app --host 0.0.0.0 --port $PORT` y la ruta de comprobación `/`. Configura `MONGO_URI` y `JWT_SECRET_KEY` como variables privadas en Render; usa `MONGO_DB_NAME=techgear_shop`, `JWT_ACCESS_TOKEN_MINUTES=30` y Python `3.14.7`. No guardes los valores secretos en este repositorio.

Antes de probarlo, confirma que el usuario de base de datos de Atlas tenga permisos sobre `techgear_shop` y que la lista de acceso de red permita el tráfico del servicio. Mantén el acceso restringido a las direcciones o rangos requeridos; no abras Atlas a cualquier IP como atajo.

El plan gratuito de Render puede suspender el servicio tras inactividad y tardar en despertar al recibir la siguiente solicitud. Es adecuado para demostración académica, no para una tienda en producción. La instancia gratuita de Render no permite ejecutar tareas de una sola vez desde su panel; prepara el índice y crea la cuenta administrativa desde tu computador con `.env` local apuntando a Atlas.

## Pruebas y calidad

Desde la raíz del repositorio:

```powershell
& ./techgear_api/.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
& ./techgear_api/.venv/Scripts/python.exe -m ruff check .
& ./techgear_api/.venv/Scripts/python.exe -m ruff format --check .
$env:PYTHONPATH = (Resolve-Path ./techgear_api).Path
& ./techgear_api/.venv/Scripts/python.exe -m unittest discover -s techgear_api/tests -v
Remove-Item Env:PYTHONPATH
& ./techgear_web/.venv/Scripts/python.exe techgear_web/manage.py check
& ./techgear_web/.venv/Scripts/python.exe techgear_web/manage.py test config --verbosity 2
& ./techgear_api/.venv/Scripts/python.exe -m pip check
& ./techgear_web/.venv/Scripts/python.exe -m pip check
git diff --check
```

Las pruebas automáticas simulan MongoDB y no necesitan credenciales de Atlas ni escriben en la base de datos.

## Control de versiones

El taller avanza secuencialmente en `main`, con un solo commit por clase y mensajes Conventional Commits.

## Django y MongoDB

Se conserva Django como interfaz MVT que consumirá FastAPI por HTTP. Las cuentas de clientes, productos y pedidos se administran centralmente en la API; no se duplican usuarios con el modelo nativo de Django. La configuración inicial de componentes internos de Django utiliza `django-mongodb-backend` 6.1.x sin ejecutar migraciones en esta etapa.

La configuración sigue la [guía oficial de MongoDB](https://www.mongodb.com/docs/languages/python/django-mongodb/v5.2/get-started/) y la [plantilla oficial, revisión 3c0170f](https://github.com/mongodb-labs/django-mongodb-project/tree/3c0170f6e6f9d110123e17e91d3c30c928c5dc0b).
