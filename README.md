# Techgear_Shop

Taller 2 de APIs: tienda de hardware y accesorios tecnológicos con FastAPI, Django y MongoDB Atlas.

## Arquitectura

- `techgear_api/app/main.py`: aplicación FastAPI y ciclo de vida de la conexión.
- `techgear_api/app/core/`: configuración validada del entorno.
- `techgear_api/app/db/`: conexión a MongoDB y preparación explícita de colecciones.
- `techgear_api/app/schemas/`: esquemas Pydantic de productos y pedidos.
- `techgear_api/tests/`: pruebas con datos ficticios y conexiones simuladas.
- `techgear_web/config/`: configuración inicial del proyecto Django MVT.
- `pyproject.toml`: reglas compartidas de formato y análisis con Ruff.

## Alcance funcional

- Productos reales con SKU único, nombre, marca, categoría, descripción, especificaciones técnicas, precio en COP, existencias, URL de imagen y estado activo.
- Registro de clientes por cuenta propia y por un administrador.
- Carrito con cantidades, subtotales y total. Editar o abandonar el carrito no modifica existencias en MongoDB.
- Confirmación del carrito: validación de disponibilidad, registro del pedido y descuento de existencias.
- Administración de productos, existencias y estados de los pedidos.
- Registro interno del proceso posterior, sin integración con pagos ni transportadoras.

## Clase 1

Se incluyen los entornos independientes, la estructura base, la conexión a MongoDB y los esquemas de entrada y salida. La API expone una ruta informativa en `/` y Swagger en `/docs`. Los endpoints de productos y pedidos, las cuentas, el carrito y las interfaces de negocio corresponden a etapas posteriores.

Toda la persistencia utiliza MongoDB en la base `techgear_shop`: Django gestionará usuarios, permisos y sesiones mediante Django MongoDB Backend; FastAPI gestionará productos y pedidos mediante PyMongo. En esta etapa se prepara la configuración, sin ejecutar migraciones de Django ni crear usuarios. Django incluye las migraciones compatibles con ObjectId de la plantilla oficial de MongoDB.

Las contraseñas se gestionarán mediante el sistema de autenticación y hashing de Django. La interfaz accederá a productos y pedidos a través de FastAPI; Django solo accederá directamente a las colecciones de sus componentes internos.

La aplicación debe ejecutarse en un servidor accesible para utilizarla desde otros equipos. MongoDB centraliza la persistencia; la configuración actual de los servidores sigue limitada a localhost.

## Requisitos

- Python 3.14.
- Acceso a MongoDB Atlas y una URI válida con los permisos requeridos para la base del proyecto.
- PowerShell para ejecutar los comandos siguientes desde la raíz del repositorio.

## Instalación

```powershell
python -m venv techgear_api/.venv
& ./techgear_api/.venv/Scripts/python.exe -m pip install -r techgear_api/requirements.txt
python -m venv techgear_web/.venv
& ./techgear_web/.venv/Scripts/python.exe -m pip install -r techgear_web/requirements.txt
```

Crear `techgear_api/.env` a partir de `techgear_api/.env.example` y `techgear_web/.env` a partir de `techgear_web/.env.example` solo si aún no existen. Los archivos privados no se versionan.

| Variable | Aplicación | Uso |
| --- | --- | --- |
| `MONGO_URI` | API y Web | URI privada de MongoDB Atlas. |
| `MONGO_DB_NAME` | API y Web | Base del proyecto: `techgear_shop`. |
| `DJANGO_SECRET_KEY` | Web | Clave privada de Django, generada localmente. |
| `DJANGO_DEBUG` | Web | `True` para desarrollo local; `False` fuera de ese entorno. |
| `DJANGO_ALLOWED_HOSTS` | Web | Hosts permitidos separados por comas. |
| `TECHGEAR_API_URL` | Web | Dirección de la API; localmente `http://127.0.0.1:8001`. |

Para generar una clave local de Django:

```powershell
& ./techgear_web/.venv/Scripts/python.exe -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Guardar la clave generada en el `.env` de Django. Nunca incorporarla a commits.

## MongoDB

Desde `techgear_api`, verificar la conexión sin escribir datos:

```powershell
& ./.venv/Scripts/python.exe -m app.db.mongodb
```

Para preparar explícitamente la base configurada:

```powershell
& ./.venv/Scripts/python.exe -m app.db.mongodb --initialize
```

Este comando crea las colecciones `products` y `orders` si no existen y asegura un índice único en `products.sku`. No inserta productos, pedidos ni datos de demostración. El inicio normal de la API verifica la conexión y no crea colecciones.

## Ejecución local

Primera terminal, desde la raíz:

```powershell
& ./techgear_api/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir techgear_api --host 127.0.0.1 --port 8001 --reload
```

Segunda terminal, desde la raíz:

```powershell
& ./techgear_web/.venv/Scripts/python.exe techgear_web/manage.py runserver 127.0.0.1:8000
```

- API: <http://127.0.0.1:8001/>
- Swagger UI: <http://127.0.0.1:8001/docs>
- Django: <http://127.0.0.1:8000/>

Estos servidores son para desarrollo local. Django puede advertir sobre migraciones pendientes en este esqueleto inicial.

## Esquemas

Los esquemas se encuentran en `app/schemas/`. `ProductCreate` valida datos de producto; `ProductRead` añade su identificador. `OrderCreate` recibe exclusivamente identificadores de producto y cantidades. La identidad del cliente autenticado y los precios se obtendrán en el servidor cuando se implemente la creación de pedidos.

`OrderRead` incluye el cliente, los productos con copia del SKU, nombre y precio, los subtotales, el total en COP, la fecha con zona horaria y el estado. Los importes utilizan `Decimal`, con hasta dos decimales. Se valida la igualdad entre subtotal y precio por cantidad, y entre total y suma de subtotales. No se realizan conversiones a `float`. La conversión explícita a tipos BSON se implementará con la persistencia.

| Estado interno | Significado |
| --- | --- |
| `confirmed` | Confirmado |
| `preparing` | En preparación |
| `shipped` | Enviado |
| `delivered` | Entregado |
| `cancelled` | Cancelado |

## Calidad y pruebas

Desde la raíz:

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

Las pruebas automáticas no requieren credenciales ni escriben en MongoDB Atlas.

## Control de versiones

Trabajo progresivo y secuencial exclusivamente sobre `main`. Las convenciones y comprobaciones previas a publicar se describen en [CONTRIBUTING.md](CONTRIBUTING.md).

## Integración Django y MongoDB

Se utiliza `django-mongodb-backend` 5.2.x con Django 5.2.x. `config/apps.py`, `DEFAULT_AUTO_FIELD` y `mongo_migrations/` adaptan los componentes internos de Django a identificadores ObjectId. Las migraciones están versionadas, sin aplicarse en esta etapa.

La configuración se basa en la [guía oficial de MongoDB](https://www.mongodb.com/docs/languages/python/django-mongodb/v5.2/get-started/) y en la [plantilla oficial, revisión 3c0170f](https://github.com/mongodb-labs/django-mongodb-project/tree/3c0170f6e6f9d110123e17e91d3c30c928c5dc0b).

Las reglas de trabajo y los límites de alcance del proyecto están en [AGENTS.md](AGENTS.md).
