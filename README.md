# Techgear Shop

Tienda de componentes de computador desarrollada para el Taller 2 de APIs. Integra una API de negocio con FastAPI, una interfaz Django bajo el patrón MVT y persistencia en MongoDB Atlas.

**Autor:** [Juan Esteban Maya · Yojemr](https://github.com/Yojemr)

**Entrega:** versión `1.0.0`, publicada como release `v1.0`.

## Enlaces del proyecto

| Recurso          | Enlace                                                                                                                                                         | Para qué sirve                                                             |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| Tienda web       | [Abrir Techgear Shop](https://techgear-shop-ten.vercel.app/)                                                                                                   | Consultar componentes, registrarse, preparar el carrito y revisar pedidos. |
| Registro         | [Crear cuenta](https://techgear-shop-ten.vercel.app/registro/)                                                                                                 | Registrar una cuenta de cliente.                                           |
| Inicio de sesión | [Ingresar](https://techgear-shop-ten.vercel.app/ingresar/)                                                                                                     | Acceder como cliente o administrador.                                      |
| API              | [Servicio en Render](https://techgear-shop-api.onrender.com/)                                                                                                  | Comprobar que el servicio responde.                                        |
| Swagger UI       | [Documentación interactiva](https://techgear-shop-api.onrender.com/docs)                                                                                       | Consultar contratos y probar operaciones de la API.                        |
| OpenAPI          | [Esquema JSON](https://techgear-shop-api.onrender.com/openapi.json)                                                                                            | Inspeccionar rutas, parámetros y esquemas de entrada y salida.             |
| Repositorio      | [Yojemr/Techgear_Shop](https://github.com/Yojemr/Techgear_Shop)                                                                                                | Consultar código e historial de `main`.                                    |
| Calidad          | [GitHub Actions](https://github.com/Yojemr/Techgear_Shop/actions/workflows/quality.yml)                                                                        | Consultar los resultados de pruebas y validaciones de cada publicación.    |
| Entrega final    | [Release v1.0](https://github.com/Yojemr/Techgear_Shop/releases/tag/v1.0)                                                                                      | Descargar el código de la entrega y leer sus notas.                        |
| Catálogo         | [Fuentes de precios y especificaciones](docs/catalog_sources.md)                                                                                               | Revisar las referencias utilizadas para los productos de demostración.     |
| Guía académica   | [Instrucciones del Taller 2](https://proud-pin-7d7.notion.site/Taller2-Python-TechGear-Sistema-H-brido-de-Cat-logo-y-Pedidos-3b977e4d98fb80c580a6ce899221c318) | Consultar el alcance, el plan de desarrollo y los requisitos de entrega.   |

### Activar la API en Render

Si la tienda indica que la API no está disponible porque el servicio gratuito se suspendió por inactividad:

1. Abre [Activar la API en Render](https://techgear-shop-api.onrender.com/).
2. Espera a que termine de despertar. La respuesta correcta muestra `"status": "ok"`; la primera solicitud puede tardar.
3. Si aún no responde, espera y vuelve a abrir el enlace. Después regresa a [la tienda](https://techgear-shop-ten.vercel.app/) y recarga la página.
4. Puedes abrir [Swagger](https://techgear-shop-api.onrender.com/docs) para comprobar que la API ya está disponible.

Este enlace despierta un servicio suspendido; si el despliegue falló o el error persiste, revisa los registros del servicio en [el panel de Render](https://dashboard.render.com/).

## Contenido

- [Funcionalidades](#funcionalidades)
- [Arquitectura y patrón MVT](#arquitectura-y-patrón-mvt)
- [Tecnologías y librerías](#tecnologías-y-librerías)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Instalación local](#instalación-local)
- [Cómo usar la tienda](#cómo-usar-la-tienda)
- [Inventario y estados del pedido](#inventario-y-estados-del-pedido)
- [API y Swagger](#api-y-swagger)
- [Errores y recuperación](#errores-y-recuperación)
- [Pruebas y calidad](#pruebas-y-calidad)
- [Despliegue](#despliegue)
- [Versionado y entrega](#versionado-y-entrega)
- [Referencias](#referencias)

## Funcionalidades

| Perfil        | Operaciones disponibles                                                                                                                                                                                   |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Visitante     | Explorar, buscar, filtrar y ordenar el catálogo; consultar fichas técnicas y sugerencias; guardar una selección en el carrito sin reservar inventario.                                                    |
| Cliente       | Registrarse, iniciar y cerrar sesión; reservar productos, cambiar cantidades, vaciar el carrito, confirmar pedidos y consultar su estado y novedades.                                                     |
| Administrador | Crear, consultar, editar, desactivar y reactivar productos; revisar pedidos de otros usuarios, prepararlos, registrar envío y entrega, rechazarlos, registrar devoluciones y publicar novedades internas. |

El catálogo inicial incluye 16 referencias: procesadores, tarjetas gráficas, placas madre, memorias RAM, SSD, fuentes de alimentación, gabinetes y refrigeración. Cada producto nuevo se carga con 5 unidades de demostración. Repetir la carga conserva los productos y existencias que ya estaban registrados.

Los precios en COP son referencias consultadas el 29 y el 30 de octubre de 2026; no se actualizan automáticamente. Las especificaciones y fuentes están en [docs/catalog_sources.md](docs/catalog_sources.md).

Confirmar un pedido registra la compra solicitada sin realizar cobros. El proyecto no integra pasarelas de pago, reembolsos, transportadoras, correo ni WhatsApp. Las notificaciones aparecen dentro de **Mis pedidos**.

## Arquitectura y patrón MVT

```text
Navegador
    │ HTML, formularios y cookie de sesión
    ▼
Django: interfaz MVT en Vercel
    │ HTTP + JWT guardado en la sesión del servidor
    ▼
FastAPI: reglas de negocio en Render
    │ PyMongo + transacciones
    ▼
MongoDB Atlas: users, products, carts y orders

Django también utiliza MongoDB Atlas para django_session.
```

FastAPI es responsable de identidad, roles, productos, precios, existencias, reservas y pedidos. Django consume sus endpoints mediante HTTP; no modifica directamente las colecciones de negocio ni duplica las cuentas comerciales con `auth.User`.

| Parte de MVT | Implementación en Django                                                                                                                                                                                                                                                  |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Models       | [models.py](techgear_web/techgear_shop/models.py) contiene modelos de presentación para carrito y pedidos. Los documentos y contratos de negocio pertenecen a FastAPI.                                                                                                    |
| Views        | [views.py](techgear_web/techgear_shop/views.py), [cart.py](techgear_web/techgear_shop/cart.py), [dashboard.py](techgear_web/techgear_shop/dashboard.py) y [order_dashboard.py](techgear_web/techgear_shop/order_dashboard.py) atienden las páginas y validan formularios. |
| Templates    | [templates/techgear_shop](techgear_web/techgear_shop/templates/techgear_shop) contiene las páginas y fragmentos HTML renderizados en el servidor.                                                                                                                         |
| Consumo HTTP | [services/api.py](techgear_web/techgear_shop/services/api.py) centraliza las solicitudes a FastAPI, los tiempos de espera y los errores públicos.                                                                                                                         |

La autenticación utiliza contraseñas con hash Argon2 y JWT de duración limitada. El navegador recibe una cookie de sesión HttpOnly; el JWT se conserva en el servidor. Los formularios Django cuentan con protección CSRF y ambas aplicaciones comprueban los permisos administrativos.

## Tecnologías y librerías

Las versiones exactas se mantienen en [requirements de la API](techgear_api/requirements.txt), [requirements de la web](techgear_web/requirements.txt) y [requirements de desarrollo](requirements-dev.txt) para reproducir las instalaciones.

| Tecnología o librería           | Versión del proyecto       | Uso                                                         |
| ------------------------------- | -------------------------- | ----------------------------------------------------------- |
| Python                          | 3.14; API fijada en 3.14.7 | Lenguaje de ambas aplicaciones.                             |
| FastAPI                         | 0.161.1                    | API REST y documentación Swagger/OpenAPI.                   |
| Pydantic / Pydantic Settings    | 2.14.1 / 2.16.1            | Validación de contratos y configuración del entorno.        |
| Uvicorn                         | 0.54.0                     | Servidor ASGI de FastAPI.                                   |
| PyMongo                         | 4.19.0                     | Conexión asíncrona con Atlas y operaciones transaccionales. |
| PyJWT                           | 2.15.1                     | Firma y validación de tokens de acceso.                     |
| pwdlib con Argon2               | 0.3.1                      | Hash y verificación de contraseñas.                         |
| python-dotenv                   | 1.2.4                      | Lectura de configuración privada local.                     |
| Django                          | 6.1.2                      | Interfaz MVT, formularios, sesiones y plantillas.           |
| django-mongodb-backend          | 6.1.0                      | Persistencia de componentes internos de Django en MongoDB.  |
| HTTPX                           | 0.28.1                     | Comunicación HTTP desde Django y pruebas de la API.         |
| Ruff                            | 0.17.2                     | Formato y análisis estático del código.                     |
| HTML, CSS y JavaScript          | Recursos propios           | Catálogo, carrusel, modal de edición y carrito lateral.     |
| MongoDB Atlas / Render / Vercel | Servicios externos         | Base de datos, despliegue de la API y despliegue de la web. |

Las pruebas utilizan `unittest` y las herramientas de prueba de Django, sin depender de cuentas o datos reales de Atlas.

## Estructura del proyecto

```text
Techgear_Shop/
├── .github/workflows/quality.yml       # Comprobaciones de calidad en GitHub
├── docs/catalog_sources.md            # Fuentes del catálogo
├── scripts/                          # Inicio y cierre de servidores locales
├── techgear_api/
│   ├── app/
│   │   ├── api/                      # Autenticación, usuarios, productos, carrito y pedidos
│   │   ├── core/                     # Configuración y seguridad
│   │   ├── db/                       # Conexión, índices y carga del catálogo
│   │   ├── schemas/                  # Contratos Pydantic
│   │   ├── services/cart.py          # Reservas e inventario transaccional
│   │   ├── cli.py                    # Comandos administrativos explícitos
│   │   └── main.py                   # Aplicación FastAPI
│   ├── data/pc_components.json        # Productos iniciales con fuentes
│   ├── tests/                        # Pruebas aisladas de la API
│   ├── .env.example
│   └── requirements.txt
├── techgear_web/
│   ├── config/                       # Configuración y entradas WSGI/ASGI
│   ├── mongo_migrations/             # Migraciones de componentes internos de Django
│   ├── techgear_shop/
│   │   ├── services/api.py           # Cliente HTTP de FastAPI
│   │   ├── static/techgear_shop/     # CSS, JavaScript, iconos e ilustraciones
│   │   ├── templates/techgear_shop/  # Plantillas públicas y administrativas
│   │   ├── models.py                # Modelos de presentación
│   │   ├── forms.py                 # Validación de formularios
│   │   ├── middleware.py            # Comprobación de identidad y sesión
│   │   ├── views.py                 # Catálogo, registro y autenticación
│   │   ├── cart.py                  # Carrito y consulta de pedidos propios
│   │   ├── dashboard.py             # CRUD administrativo de productos
│   │   ├── order_dashboard.py       # Gestión administrativa de pedidos
│   │   └── urls.py                  # Rutas de la tienda
│   ├── .env.example
│   ├── manage.py
│   ├── requirements.txt
│   └── vercel.json
├── iniciar_local.cmd
├── cerrar_local.cmd
├── pyproject.toml
├── requirements-dev.txt
└── README.md
```

Los archivos `.env`, entornos virtuales, credenciales, cachés y resultados generados se excluyen de Git.

## Instalación local

Los siguientes pasos usan PowerShell en Windows. Ejecuta los comandos desde la raíz del repositorio, salvo cuando se indique otra ubicación.

### 1. Obtener el proyecto

Se necesita Git, Python 3.14 y una base MongoDB Atlas con acceso de red y permisos para el proyecto.

```powershell
git clone https://github.com/Yojemr/Techgear_Shop.git
cd Techgear_Shop
python --version
```

Si ya tienes el repositorio, abre su carpeta en Visual Studio Code y utiliza su terminal integrada.

### 2. Preparar los entornos independientes

```powershell
python -m venv techgear_api/.venv
& ./techgear_api/.venv/Scripts/python.exe -m pip install -r techgear_api/requirements.txt
python -m venv techgear_web/.venv
& ./techgear_web/.venv/Scripts/python.exe -m pip install -r techgear_web/requirements.txt
```

Los comandos invocan cada intérprete directamente; no es necesario activar un entorno ni cambiar la política de ejecución de PowerShell. La interfaz no requiere Node.js para ejecutarse.

### 3. Configurar las variables privadas

Copia los ejemplos solo si todavía no existen los archivos locales:

```powershell
if (-not (Test-Path ./techgear_api/.env)) { Copy-Item ./techgear_api/.env.example ./techgear_api/.env }
if (-not (Test-Path ./techgear_web/.env)) { Copy-Item ./techgear_web/.env.example ./techgear_web/.env }
```

| Variable                      | Aplicación | Configuración                                                        |
| ----------------------------- | ---------- | -------------------------------------------------------------------- |
| `MONGO_URI`                   | API y web  | URI privada de Atlas. Usar el mismo clúster para ambas aplicaciones. |
| `MONGO_DB_NAME`               | API y web  | `techgear_shop`, separada de otras bases del clúster.                |
| `JWT_SECRET_KEY`              | API        | Clave privada aleatoria de al menos 32 bytes.                        |
| `JWT_ACCESS_TOKEN_MINUTES`    | API        | Duración de acceso; valor predeterminado: `30`.                      |
| `DJANGO_SECRET_KEY`           | Web        | Clave privada aleatoria y estable.                                   |
| `DJANGO_DEBUG`                | Web        | `True` durante el desarrollo local; `False` al desplegar.            |
| `DJANGO_ALLOWED_HOSTS`        | Web        | Localmente: `127.0.0.1,localhost`.                                   |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Web        | Orígenes HTTPS adicionales cuando se usa un dominio propio.          |
| `TECHGEAR_API_URL`            | Web        | Localmente: `http://127.0.0.1:8001`.                                 |

En Atlas, abre **Connect → Drivers**, copia la URI y completa usuario y contraseña con las credenciales de acceso a la base. Conserva la URI únicamente en los archivos privados o variables del servicio. Configura permisos y acceso de red para la base del proyecto.

Puedes generar cada clave privada con este comando; ejecútalo por separado para JWT y Django y guarda los resultados en sus respectivos archivos `.env`:

```powershell
& ./techgear_api/.venv/Scripts/python.exe -c "import secrets; print(secrets.token_hex(32))"
```

### 4. Preparar las colecciones y las sesiones

La preparación es explícita e idempotente. No se ejecuta automáticamente al iniciar los servicios:

```powershell
$env:PYTHONPATH = (Resolve-Path ./techgear_api).Path
& ./techgear_api/.venv/Scripts/python.exe -m app.db.mongodb --initialize
Remove-Item Env:PYTHONPATH
& ./techgear_web/.venv/Scripts/python.exe techgear_web/manage.py migrate sessions
```

La API prepara `users`, `products`, `carts` y `orders`, junto con sus índices. Django prepara `django_session` en MongoDB. Estas migraciones son para componentes internos; no trasladan ni recrean las cuentas comerciales.

### 5. Cargar el catálogo y crear un administrador

Estos comandos escriben en la base configurada. Ejecútalos solo cuando corresponda preparar esa base:

```powershell
$env:PYTHONPATH = (Resolve-Path ./techgear_api).Path
& ./techgear_api/.venv/Scripts/python.exe -m app.cli seed-catalog --stock 5
& ./techgear_api/.venv/Scripts/python.exe -m app.cli create-admin
Remove-Item Env:PYTHONPATH
```

La carga incorpora únicamente SKU que todavía no existen. El alta administrativa solicita nombre, correo y contraseña de forma interactiva; la contraseña no se muestra en pantalla. **No existe una cuenta administrativa predeterminada.**

### 6. Iniciar y detener la tienda

```powershell
.\iniciar_local.cmd
```

El lanzador utiliza los entornos existentes, inicia API y web, y abre el catálogo cuando ambos responden. Usa la API local y `DJANGO_DEBUG=True` para esa ejecución sin modificar los archivos `.env`.

| Servicio local | Enlace                                                   |
| -------------- | -------------------------------------------------------- |
| Tienda         | [http://127.0.0.1:8000/](http://127.0.0.1:8000/)         |
| API            | [http://127.0.0.1:8001/](http://127.0.0.1:8001/)         |
| Swagger UI     | [http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs) |

Mantén la consola abierta. `Ctrl+C` detiene los servicios creados por el lanzador. Desde otra terminal puedes ejecutar:

```powershell
.\cerrar_local.cmd
```

El cierre identifica servidores de este repositorio y conserva los procesos de otros proyectos. Los lanzadores también pueden abrirse con doble clic.

| Opción                             | Efecto                                                             |
| ---------------------------------- | ------------------------------------------------------------------ |
| `.\iniciar_local.cmd --check`      | Comprueba entornos, configuración y puertos sin iniciar servicios. |
| `.\iniciar_local.cmd --no-browser` | Inicia ambos servicios sin abrir el navegador.                     |
| `.\cerrar_local.cmd --check`       | Comprueba servidores locales sin cerrarlos.                        |

Para iniciar los servicios por separado, utiliza dos terminales en la raíz:

```powershell
# Terminal 1: API
& ./techgear_api/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir techgear_api --host 127.0.0.1 --port 8001 --reload
```

```powershell
# Terminal 2: web
& ./techgear_web/.venv/Scripts/python.exe techgear_web/manage.py runserver 127.0.0.1:8000
```

## Cómo usar la tienda

### Recorrido del cliente

1. Explora el catálogo y abre la ficha de un componente para consultar sus especificaciones y sugerencias.
2. Añade productos al carrito lateral. Sin sesión, la selección no reserva inventario.
3. Crea una cuenta e inicia sesión. La API intenta reservar toda la selección; si faltan unidades, podrás ajustar las cantidades pendientes y pulsar **Reservar selección**.
4. Revisa cantidades, subtotales y total. Los precios se validan nuevamente en el servidor.
5. Pulsa **Confirmar pedido**. Se registra un pedido sin cobro y aparece su comprobante.
6. Abre **Mis pedidos** desde el menú de la cuenta para consultar el estado y las novedades publicadas por la tienda.
7. Al cerrar sesión, las unidades que todavía estén reservadas en el carrito regresan al inventario.

### Recorrido del administrador

1. Ingresa con la cuenta administrativa creada mediante el comando de preparación.
2. Abre **Administración → Productos e inventario** para crear componentes o buscar, filtrar, editar y desactivar los existentes.
3. **Editar** abre un modal con datos técnicos, precio, existencias y visibilidad. Sin JavaScript, el enlace conserva el formulario tradicional.
4. Abre **Pedidos de clientes**, filtra por estado y pulsa **Revisar pedido**.
5. Revisa cliente, piezas, cantidades e importes. Usa las acciones disponibles para aceptar y preparar, registrar envío o entrega, rechazar antes del envío o registrar la devolución después de entregar.
6. Escribe una novedad y pulsa **Notificar al cliente** para dejar un mensaje visible en el detalle de su pedido.

Las acciones administrativas exigen rol de administrador tanto en Django como en FastAPI. Desactivar un producto no borra sus referencias históricas. El registro administrativo de nuevos clientes también está disponible en `POST /users/` de la API.

## Inventario y estados del pedido

`products.stock` representa las unidades disponibles para nuevas reservas, excluyendo las que están en carritos autenticados.

| Acción                                                       | Efecto sobre el inventario                                                                                     |
| ------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------- |
| Visitante añade o modifica su selección                      | No descuenta unidades.                                                                                         |
| Cliente autenticado añade unidades                           | Reserva y descuenta la diferencia en una transacción de MongoDB.                                               |
| Otro cliente intenta tomar esas unidades                     | Solo puede reservar el stock restante.                                                                         |
| Cliente reduce cantidad, retira productos o vacía el carrito | Devuelve las unidades liberadas.                                                                               |
| Cliente confirma un carrito                                  | Convierte la reserva en pedido sin volver a descontar. Repetir la misma confirmación devuelve el mismo pedido. |
| Administrador rechaza antes del envío                        | Cancela el pedido y repone sus unidades una sola vez.                                                          |
| Administrador registra una devolución después de la entrega  | Devuelve el pedido completo y repone sus unidades una sola vez.                                                |
| Administrador guarda una ficha con stock antiguo             | La API rechaza la escritura; debe abrir de nuevo la edición para consultar las existencias actuales.           |

Los cambios de carrito, pedido e inventario que deban realizarse juntos usan transacciones. Un fallo revierte los cambios parciales. Los importes se calculan con `Decimal` y se guardan con precisión decimal; cada pedido conserva el SKU, nombre y precio de sus productos al confirmar.

Las pestañas autenticadas notifican presencia cada 30 segundos. Si pasan 120 segundos sin señal, la reserva vence y la siguiente consulta al catálogo, carrito o compra la libera transaccionalmente. Cerrar el navegador, una desconexión prolongada o su suspensión pueden liberar la reserva sin cerrar la cuenta. No se usa un índice TTL que borre reservas sin devolver stock.

| Estado API  | Presentación          | Siguiente acción permitida     |
| ----------- | --------------------- | ------------------------------ |
| `confirmed` | Confirmado            | Aceptar y preparar o rechazar. |
| `preparing` | En preparación        | Marcar enviado o rechazar.     |
| `shipped`   | Enviado               | Marcar entregado.              |
| `delivered` | Entregado             | Registrar devolución completa. |
| `cancelled` | Rechazado / cancelado | Estado final.                  |
| `returned`  | Devuelto              | Estado final.                  |

Cada cambio administrativo deja una novedad en el pedido. Las notificaciones internas pueden reintentarse con el mismo identificador sin duplicar el mensaje. Ningún estado representa un pago realizado.

## API y Swagger

Abre [Swagger publicado](https://techgear-shop-api.onrender.com/docs) o [Swagger local](http://127.0.0.1:8001/docs).

1. Registra un cliente mediante `POST /auth/register` o utiliza una cuenta existente.
2. Ejecuta `POST /auth/login` con correo y contraseña.
3. Copia `access_token` y pégalo en **Authorize**. Se utilizará como token Bearer.
4. Prueba las rutas correspondientes a tu rol. Los precios y la identidad del cliente los determina la API.
5. Usa **Logout** en el cuadro de autorización para retirar el token del navegador de Swagger al terminar.

| Método y ruta                                        | Acceso        | Operación                                                                              |
| ---------------------------------------------------- | ------------- | -------------------------------------------------------------------------------------- |
| `GET /`                                              | Público       | Identificación del servicio.                                                           |
| `POST /auth/register`                                | Público       | Crear cliente; el rol no se recibe desde el formulario.                                |
| `POST /auth/login`                                   | Público       | Obtener JWT y vencimiento.                                                             |
| `GET /users/me`                                      | Autenticado   | Consultar el perfil vigente.                                                           |
| `POST /users/`                                       | Administrador | Registrar un cliente.                                                                  |
| `GET /products/`, `GET /products/{id}`               | Público       | Consultar productos activos.                                                           |
| `GET /products/manage/`, `GET /products/manage/{id}` | Administrador | Consultar productos, incluidos inactivos.                                              |
| `POST /products/`                                    | Administrador | Crear un componente.                                                                   |
| `PUT /products/{id}`                                 | Administrador | Editar con `expected_stock` para proteger reservas concurrentes.                       |
| `DELETE /products/{id}`                              | Administrador | Desactivar sin eliminar el documento.                                                  |
| `GET /cart/`                                         | Autenticado   | Consultar carrito propio y totales.                                                    |
| `POST /cart/items/{id}`                              | Autenticado   | Añadir y reservar unidades.                                                            |
| `PUT /cart/items/{id}`                               | Autenticado   | Fijar cantidad; cero retira la línea.                                                  |
| `DELETE /cart/`                                      | Autenticado   | Vaciar y devolver reservas.                                                            |
| `POST /cart/import`                                  | Autenticado   | Reservar la selección de visitante de forma atómica e idempotente.                     |
| `POST /cart/heartbeat`                               | Autenticado   | Renovar una reserva vigente.                                                           |
| `POST /cart/checkout`                                | Autenticado   | Confirmar versión y total sin duplicar pedido ni descuento.                            |
| `POST /orders/`                                      | Autenticado   | Crear directamente un pedido con productos y cantidades, descontando stock disponible. |
| `GET /orders/`, `GET /orders/{id}`                   | Autenticado   | Consultar pedidos propios; los administradores pueden consultar todos.                 |
| `PATCH /orders/{id}/status`                          | Administrador | Aplicar transiciones y devolver stock cuando corresponda.                              |
| `POST /orders/{id}/notifications`                    | Administrador | Publicar una novedad interna.                                                          |

La web confirma su carrito reservado mediante `/cart/checkout`; el endpoint directo `/orders/` es una operación diferente y no consume reservas existentes. En las listas de pedidos se admiten `limit`, `offset`, `mine` y `order_status`.

## Errores y recuperación

| Situación                                                  | Comportamiento y siguiente paso                                                                                                        |
| ---------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| API caída, sin conexión o respuesta lenta                  | La web muestra un mensaje controlado. Un fallo temporal no borra la sesión. Vuelve a intentar la consulta cuando el servicio responda. |
| Producto sin stock o cantidades reservadas por otra cuenta | La API responde `409`; no completa reservas parciales. Ajusta las cantidades y revisa el carrito.                                      |
| Precio o versión del carrito cambió                        | La confirmación se rechaza hasta revisar los datos actuales.                                                                           |
| Edición de producto con inventario desactualizado          | La API responde `412`. Abre otra vez la ficha y revisa existencias antes de guardar.                                                   |
| Sesión vencida o token rechazado                           | La cuenta debe iniciar sesión de nuevo.                                                                                                |
| Usuario sin permisos administrativos                       | Se bloquea la operación con `403`.                                                                                                     |
| Producto o pedido no disponible                            | Se muestra una página de error con navegación de recuperación; consultar un pedido no se presenta como un error de producto.           |
| Datos inválidos o formulario sin protección CSRF           | La operación se rechaza y el formulario muestra sus errores cuando corresponde.                                                        |
| Respuesta perdida al confirmar                             | Consulta **Mis pedidos** antes de repetir. La misma versión de carrito no genera dos pedidos.                                          |
| Falla al devolver reservas durante el cierre de sesión     | La web conserva la sesión para permitir reintentar el cierre.                                                                          |

Si un puerto local está ocupado, utiliza `cerrar_local.cmd --check` para revisar los servidores del proyecto antes de iniciar otra instancia. Si cambias CSS o JavaScript y el navegador conserva una versión anterior, recarga con `Ctrl+F5`.

## Pruebas y calidad

Desde la raíz, instala las herramientas de desarrollo en el entorno de la API:

```powershell
& ./techgear_api/.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
```

Ejecuta las pruebas y validaciones:

```powershell
$env:PYTHONPATH = (Resolve-Path ./techgear_api).Path
& ./techgear_api/.venv/Scripts/python.exe -m unittest discover -s techgear_api/tests -v
Remove-Item Env:PYTHONPATH
& ./techgear_web/.venv/Scripts/python.exe techgear_web/manage.py test config techgear_shop --verbosity 2
& ./techgear_api/.venv/Scripts/python.exe -m ruff check .
& ./techgear_api/.venv/Scripts/python.exe -m ruff format --check .
& ./techgear_api/.venv/Scripts/python.exe -m pip check
& ./techgear_web/.venv/Scripts/python.exe -m pip check
git diff --check
```

La suite de la entrega contiene 42 pruebas de API y 75 de Django. Comprueba permisos, sesiones, contratos, errores, reservas simultáneas, confirmación idempotente, reversiones transaccionales y devolución de inventario. Utiliza datos ficticios y almacenamiento simulado; no necesita credenciales reales de Atlas ni modifica sus colecciones.

El flujo [Quality](.github/workflows/quality.yml) ejecuta las pruebas y comprobaciones en cada push a `main` y en los pull requests dirigidos a ella. Sus permisos se limitan a lectura del repositorio.

Para una revisión manual, utiliza una base de pruebas: recorre registro, login, carrito, confirmación, historial y gestión administrativa. Con 5 unidades iniciales, reservar 3 debe dejar 2 disponibles; confirmar no debe restarlas otra vez, y rechazar el pedido debe devolver las 3 unidades.

## Despliegue

### API en Render

Conecta el repositorio a un servicio web Python con estos valores:

| Campo             | Valor                                              |
| ----------------- | -------------------------------------------------- |
| Rama              | `main`                                             |
| Root Directory    | `techgear_api`                                     |
| Build Command     | `pip install -r requirements.txt`                  |
| Start Command     | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/`                                                |
| Python            | `3.14.7`, fijado en `techgear_api/.python-version` |

Configura como variables privadas `MONGO_URI`, `MONGO_DB_NAME=techgear_shop`, `JWT_SECRET_KEY` y `JWT_ACCESS_TOKEN_MINUTES=30`. Verifica los permisos de Atlas y su acceso de red para el servicio. El arranque no crea cuentas ni carga productos.

Cuando finalice el despliegue, abre [la API](https://techgear-shop-api.onrender.com/) y [Swagger](https://techgear-shop-api.onrender.com/docs). Comprueba que el [OpenAPI publicado](https://techgear-shop-api.onrender.com/openapi.json) incluya las rutas de carrito y gestión de pedidos de esta entrega.

En el plan gratuito, Render puede suspender el servicio por inactividad y tardar en responder al reactivarse. La web muestra el error temporal y permite reintentar; no confirma compras automáticamente durante una caída.

### Web en Vercel

Importa el mismo repositorio como proyecto Django independiente:

| Campo                   | Valor                                                                                          |
| ----------------------- | ---------------------------------------------------------------------------------------------- |
| Rama de producción      | `main`                                                                                         |
| Root Directory          | `techgear_web`                                                                                 |
| Framework Preset        | `Django`                                                                                       |
| Install / Build Command | Predeterminados del framework; dependencias de `requirements.txt` y recopilación de estáticos. |
| Output Directory        | Predeterminado, sin reemplazo manual.                                                          |
| Python                  | `3.14`, definido en `techgear_web/.python-version`                                             |

[techgear_web/vercel.json](techgear_web/vercel.json) declara el framework. La aplicación se sirve mediante `config.wsgi.application`; Django reúne los recursos en `STATIC_ROOT` y Vercel los publica en `/static/`.

Configura estas variables para los entornos de Vercel que utilices:

| Variable                      | Valor o criterio                                                    |
| ----------------------------- | ------------------------------------------------------------------- |
| `DJANGO_SECRET_KEY`           | Clave privada estable entre despliegues.                            |
| `DJANGO_DEBUG`                | `False`; la configuración también lo desactiva al detectar Vercel.  |
| `TECHGEAR_API_URL`            | `https://techgear-shop-api.onrender.com`                            |
| `MONGO_URI`                   | URI privada de Atlas para persistir las sesiones.                   |
| `MONGO_DB_NAME`               | `techgear_shop`                                                     |
| `DJANGO_ALLOWED_HOSTS`        | Dominios propios adicionales, separados por comas y sin protocolo.  |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Orígenes propios adicionales, con `https://` y separados por comas. |

Los dominios que Vercel entrega en `VERCEL_URL` y `VERCEL_PROJECT_PRODUCTION_URL` se incorporan automáticamente a los hosts y orígenes permitidos. Si no se exponen esas variables, configura el dominio exacto manualmente. Las claves y URI privadas no se incluyen en `vercel.json` ni en el repositorio.

Prepara las sesiones de Django mediante el comando local explícito antes de usar la web desplegada. La compilación no ejecuta migraciones ni necesita modificar las colecciones comerciales.

Comprueba [salud web](https://techgear-shop-ten.vercel.app/salud/), [catálogo](https://techgear-shop-ten.vercel.app/), [registro](https://techgear-shop-ten.vercel.app/registro/), [login](https://techgear-shop-ten.vercel.app/ingresar/) y [carrito](https://techgear-shop-ten.vercel.app/carrito/). Revisa también el acceso de clientes y administradores, los recursos estáticos, las cookies HTTPS y los formularios CSRF. Para compartir la tienda, utiliza su dominio de producción y verifica el acceso sin iniciar sesión en Vercel.

## Versionado y entrega

El desarrollo del taller se realiza secuencialmente sobre `main`, con commits agrupados por entrega y mensajes Conventional Commits. La release `v1.0` identifica el código final y su documentación; el número de versión de la API es `1.0.0`.

Consulta [el historial](https://github.com/Yojemr/Techgear_Shop/commits/main/), [las pruebas publicadas](https://github.com/Yojemr/Techgear_Shop/actions) y [la release](https://github.com/Yojemr/Techgear_Shop/releases/tag/v1.0). Desde la release se pueden descargar los archivos fuente en ZIP o TAR.GZ correspondientes al código etiquetado.

## Referencias

- [FastAPI](https://fastapi.tiangolo.com/): documentación del framework de la API.
- [Django](https://docs.djangoproject.com/): documentación del framework web y sus componentes.
- [Pydantic](https://docs.pydantic.dev/): esquemas y validación de datos.
- [PyMongo](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/): controlador Python para MongoDB.
- [Django MongoDB Backend](https://www.mongodb.com/docs/languages/python/django-mongodb/current/): persistencia de Django en MongoDB.
- [HTTPX](https://www.python-httpx.org/): cliente HTTP utilizado por la web.
- [FastAPI en Render](https://render.com/docs/deploy-fastapi): guía de despliegue de la API.
- [Django en Vercel](https://vercel.com/docs/frameworks/full-stack/django): guía del despliegue web.
- [Releases en GitHub](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository): publicación de entregas etiquetadas.
- [Fuentes del catálogo](docs/catalog_sources.md): precios de referencia, fotografías y especificaciones de los componentes.
