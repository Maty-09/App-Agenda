# API pública de Norem

La agenda se puede integrar de dos maneras: mediante el widget listo para usar (recomendado) o con la API para un formulario propio. Ninguna opción expone CRM, tareas, usuarios ni información de otros negocios.

## Integración rápida: un solo script

Para mostrar la agenda completa dentro de cualquier página, el cliente solo debe pegar esto donde quiera que aparezca el formulario:

```html
<script src="https://TU-DOMINIO/api/v1/public/TENANT_ID/agenda/widget.js"></script>
```

Reemplaza `TU-DOMINIO` por el dominio donde esté publicado Norem y `TENANT_ID` por el identificador entregado para ese negocio. El script inserta un iframe responsive con el formulario de reserva; no requiere instalar librerías ni copiar una clave al sitio del cliente.

También se puede obtener el enlace listo desde:

```http
GET /api/v1/public/{tenant_id}/agenda
```

La respuesta incluye `booking_url` y `embed_script`.

## Integración personalizada

Si el cliente necesita diseñar su propio formulario, puede usar los endpoints de disponibilidad y creación de reserva que se describen a continuación.

## Seguridad y activación

La API está desactivada por defecto. Un administrador del tenant debe configurarla con su token de administración:

```http
PUT /api/v1/public-api/settings
Authorization: Bearer <token-admin>
Content-Type: application/json

{
  "enabled": true,
  "allowed_origins": ["https://www.miempresa.cl"]
}
```

La respuesta entrega una `public_key`, el `availability_url` y el `booking_url`. Guarda la clave en la configuración del sitio. Es una clave de integración pública, no una credencial administrativa: solo sirve para consultar disponibilidad y crear reservas del tenant configurado.

Para invalidar una integración anterior, genera una nueva clave:

```http
POST /api/v1/public-api/settings/regenerate-key
Authorization: Bearer <token-admin>
```

Configura únicamente dominios que controles. Cada origen debe incluir el protocolo, por ejemplo `https://www.miempresa.cl`. La API valida el origen del navegador y agrega los encabezados CORS solo para esos dominios.

## 1. Consultar disponibilidad

```http
GET /api/public/v1/{tenant_id}/availability?fecha=2026-09-10&duracion_horas=2&tipo_servicio=domicilio_taller
X-Norem-Public-Key: <public_key>
```

Respuesta:

```json
{
  "fecha": "2026-09-10",
  "horas": ["09:00", "13:00", "15:30"]
}
```

Si el día está bloqueado, no es hábil o ya no tiene cupos, `horas` será un arreglo vacío.

## 2. Crear una reserva

```http
POST /api/public/v1/{tenant_id}/bookings
Content-Type: application/json
X-Norem-Public-Key: <public_key>

{
  "rut": "12345678-9",
  "nombre": "Ana",
  "apellido": "Pérez",
  "correo": "ana@example.com",
  "telefono": "+56912345678",
  "fecha": "2026-09-10",
  "hora": "09:00",
  "duracion_horas": 2,
  "tipo_servicio": "domicilio_taller",
  "subtipo": "local",
  "marca": "Toyota",
  "modelo": "Yaris",
  "patente": "ABCD12"
}
```

Respuesta exitosa (`201`):

```json
{
  "id": 123,
  "estado": "pendiente",
  "fecha_inicio": "2026-09-10T09:00:00",
  "fecha_termino": "2026-09-10T11:00:00"
}
```

Si otra persona toma el cupo antes de confirmar, la API responde `409` y el sitio debe volver a consultar disponibilidad.

## Ejemplo para una página web

```html
<script>
const API = "https://tu-norem.vercel.app/api/public/v1/TENANT_ID";
const KEY = "PUBLIC_KEY";
const headers = { "X-Norem-Public-Key": KEY };

async function cargarHoras(fecha) {
  const respuesta = await fetch(`${API}/availability?fecha=${fecha}&duracion_horas=2`, { headers });
  if (!respuesta.ok) throw new Error("No fue posible cargar la disponibilidad");
  return (await respuesta.json()).horas;
}

async function crearReserva(datos) {
  const respuesta = await fetch(`${API}/bookings`, {
    method: "POST",
    headers: { ...headers, "Content-Type": "application/json" },
    body: JSON.stringify(datos)
  });
  if (respuesta.status === 409) throw new Error("Ese horario ya fue ocupado");
  if (!respuesta.ok) throw new Error("No fue posible crear la reserva");
  return respuesta.json();
}
</script>
```

## Respuestas y límites

| Código | Significado |
| --- | --- |
| `201` | Reserva creada. |
| `401` | Falta la clave pública o no coincide. |
| `403` | El sitio web no está en los orígenes autorizados. |
| `404` | Tenant inexistente o API pública deshabilitada. |
| `409` | El horario dejó de estar disponible. Actualiza las horas. |
| `422` | Datos inválidos o tipo de servicio no habilitado. |
| `429` | Demasiadas reservas desde la misma IP. Espera y reintenta. |

La protección de tasa incluida limita a 10 intentos de reserva por IP y tenant cada 15 minutos dentro de la instancia. Para un volumen alto en producción, agrega un firewall o rate limiting distribuido delante de la aplicación.
