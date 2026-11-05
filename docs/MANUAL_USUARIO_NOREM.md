# Manual de usuario Norem

> Base de conocimiento para usuarios y para la futura mascota de soporte de Norem.
>
> Última actualización: noviembre de 2026.

## 1. Qué es Norem

Norem es una plataforma para que los negocios de servicios organicen su operación diaria en un solo lugar. Permite gestionar la agenda, reservas, clientes, tareas, configuración del negocio y, si se requiere, integrar la agenda a un sitio web propio.

Cada negocio configura Norem a su manera. Por eso los nombres de servicios, preguntas del formulario, horarios, capacidad y campos visibles pueden variar entre cuentas.

## 2. A quién está dirigido

Norem está pensado para administradores, equipos de atención y negocios de servicios. También existe una agenda pública para que los clientes de cada negocio reserven una hora.

| Tipo de persona | Qué puede hacer normalmente |
| --- | --- |
| Administrador del negocio | Configurar el negocio, horarios, formulario, equipo, reservas, clientes, tareas, API y plan. |
| Miembro del equipo | Consultar y gestionar la operación según los permisos entregados por su administrador. |
| Cliente final | Elegir una fecha y horario disponible, completar el formulario del negocio y recibir comunicaciones de su reserva. |

## 3. Primeros pasos

Al crear una cuenta de prueba, Norem guía al administrador por una configuración inicial y luego por una guía de bienvenida. Norem no trae horarios ni formularios fijos: cada negocio parte con lo que elige en estos pasos y puede cambiarlo cuando quiera.

### 3.1 Configuración inicial (al crear la cuenta)

1. **Tu negocio:** nombre, a qué se dedica y servicio principal.
2. **Cuándo atiendes:** un horario base (inicio y término), los días de atención y la duración estimada de cada atención. Es un punto de partida: en el paso 3.2 podrás definir horarios distintos por día y pausas.
3. **Datos que pedirás al cliente:** nombre, teléfono e identificación/RUT son opcionales. El **correo electrónico siempre se pide**, porque es donde el cliente recibe la confirmación de su reserva.

### 3.2 Lista de inicio recomendada

Después de la configuración inicial, conviene completar estos pasos en orden. Todos están en **Configuración del negocio**:

| Paso | Dónde | Qué revisar |
| --- | --- | --- |
| 1. Horario de atención | Configuración → **Horario de atención** | Días abiertos y cerrados, tramos de cada día, colación, feriados. |
| 2. Servicio y capacidad | Configuración → **Servicio y capacidad** | Duración de cada atención, equipos o profesionales, cada cuánto empieza un horario y anticipación mínima. |
| 3. Formulario de reserva | **Calendario** → **Formulario Local** | Agregar o quitar las preguntas que verá el cliente. |
| 4. Probar la agenda | **Ver agenda pública** | Elegir una fecha y comprobar que aparecen los horarios esperados. |
| 5. Compartir | Enlace de la agenda | Publicarlo en WhatsApp, Instagram, Google o tu sitio web. |
| 6. Integrar en tu web (opcional) | Configuración → **API pública** | Autorizar tu dominio y copiar el código. |

**Consejo:** antes de compartir el enlace, haz una reserva de prueba tú mismo y luego cancélala desde el **Calendario**.

## 4. Módulos de Norem

### 4.1 Dashboard

El dashboard resume la operación en el período seleccionado. Puede mostrar reservas de hoy, semana y mes, reservas confirmadas, pendientes o canceladas, y tareas activas o vencidas.

**Cómo usarlo:**

1. Entra a **Dashboard**.
2. Selecciona un rango de fechas o usa los accesos rápidos **Hoy**, **Semana** o **Mes**.
3. Revisa los indicadores y las tareas prioritarias.

**Importante:** los datos que aparecen dependen de lo que el negocio haya configurado y de sus reservas reales. El dashboard no debe mostrar datos de ejemplo como si fueran información real.

### 4.2 Agenda y calendario

La agenda muestra las reservas y permite al equipo consultar qué viene después.

**Para revisar una reserva:**

1. Entra a **Calendario**.
2. Busca la fecha de la atención.
3. Abre la reserva para revisar los datos ingresados por el cliente.

**Disponibilidad:** Norem muestra solo horas que cumplen las reglas que configuró el propio negocio: su horario de atención día por día, la duración de la atención, cada cuánto empieza un horario, la capacidad (equipos), la anticipación mínima, los días bloqueados y si atiende o no en feriados.

Si no aparece una hora, puede ocurrir que:

- El día esté marcado como **cerrado** en el horario de atención.
- La atención completa no quepa dentro de un tramo (por ejemplo, una atención de 2 horas no cabe en un tramo de 09:00 a 10:30).
- No haya capacidad disponible: todos los equipos ya tienen una reserva a esa hora.
- La hora esté antes de la **anticipación mínima** (por ejemplo, el negocio exige reservar con 24 horas).
- El día esté bloqueado.
- Sea un feriado y el negocio no atienda feriados.
- La fecha quede fuera de la ventana de disponibilidad futura elegida por el negocio.

**Reprogramar una cita:** desde el **Calendario**, el equipo puede mover una reserva a cualquier hora que quede dentro del horario de atención de ese día y tenga un equipo libre. Si la hora queda fuera, Norem muestra el horario de ese día para elegir otra.

### 4.3 Reservas y agenda pública

Cada negocio tiene una agenda pública que puede compartir con sus clientes. Allí el cliente elige un horario disponible y completa únicamente las preguntas que el negocio activó.

**Para compartir la agenda:**

1. Abre la agenda pública desde la configuración o desde el onboarding.
2. Copia el enlace.
3. Compártelo por redes sociales, WhatsApp, correo o el canal que prefieras.

**Para un cliente que no puede reservar:** primero confirmar la fecha, el servicio y la hora que intenta elegir. Luego revisar disponibilidad, días bloqueados, feriados y los campos obligatorios del formulario.

### 4.4 Clientes

El módulo **Clientes** concentra la información de cada persona que ha reservado: datos de contacto, historial de atenciones, notas y actividad relacionada.

**Para encontrar un cliente:**

1. Entra a **Clientes**.
2. Usa la búsqueda por nombre, correo, teléfono o identificador disponible.
3. Abre su ficha para revisar el historial y las próximas acciones.

**Buenas prácticas:** mantener los datos actualizados, escribir notas útiles para el equipo y no registrar información sensible que no sea necesaria para prestar el servicio.

### 4.5 Tareas

El módulo **Tareas** permite convertir pendientes de la operación en acciones concretas y darles seguimiento.

Una tarea puede incluir título, responsable, prioridad, estado y fecha límite, según la configuración del negocio.

**Flujo recomendado:** crear la tarea, asignar responsable, definir prioridad y fecha límite, y actualizarla cuando cambie de estado.

### 4.6 Configuración del negocio

Desde **Configuración del negocio**, el administrador ajusta cómo funciona su cuenta. Está dividida en secciones:

| Sección | Qué se configura |
| --- | --- |
| Información del negocio | Nombre, actividad y servicio principal. |
| Horario de atención | Días abiertos, tramos de cada día y atención en feriados (ver 4.7). |
| Servicio y capacidad | Duración de cada atención, equipos o profesionales, cada cuánto empieza un horario y anticipación mínima. |
| Comunicación con clientes | Si las confirmaciones incluyen la dirección y el enlace de Google Maps. |
| Disponibilidad y dashboard | Hasta cuántos días hacia adelante se puede reservar y cuántos días muestra el dashboard. |

**Servicio y capacidad en detalle:**

- **Duración de cada atención:** de 30 minutos a 8 horas. Es el tiempo que queda ocupado por cada reserva.
- **Equipos o profesionales:** escríbelos separados por coma (por ejemplo `Box 1, Box 2` o `Ana, Pedro`). Cada uno puede atender una reserva en el mismo horario, así que con dos equipos se aceptan dos reservas a la misma hora.
- **Cada cuánto empieza un horario:** por defecto, un horario empieza cuando termina el anterior (atenciones de 1 hora → 9:00, 10:00, 11:00…). Si eliges, por ejemplo, "cada 30 min", el cliente podrá reservar a las 9:00, 9:30, 10:00…
- **Anticipación mínima:** evita reservas de último minuto. Con "24 horas", hoy no se pueden tomar horas para mañana temprano.

**Regla clave:** los cambios de configuración afectan las reservas futuras y la experiencia de los clientes. Las reservas que ya existen no se modifican ni se cancelan solas. Antes de reducir horarios, revisa si tienes reservas en los días que vas a cerrar.

### 4.7 Horario de atención

Cada negocio define su propio horario, día por día. Norem no impone bloques ni horarios fijos.

**Para configurarlo:**

1. Entra a **Configuración del negocio → Horario de atención** (también desde **Calendario → Horarios de Trabajo**).
2. Marca los días en que atiendes. Los días sin marcar quedan **cerrados**.
3. En cada día abierto, escribe uno o más **tramos** con hora de inicio y término.
4. Usa **+ Agregar tramo** para sumar otro tramo al mismo día, o **Quitar** para eliminarlo.
5. Si varios días tienen el mismo horario, configura uno y usa **Copiar este horario a los demás días abiertos**.
6. Marca **Atender en feriados** solo si abres los feriados nacionales.
7. Presiona **Guardar configuración** y revisa tu agenda pública.

**Ejemplos:**

| Necesidad | Cómo se configura |
| --- | --- |
| Colación de 13:00 a 14:00 | Dos tramos: 09:00–13:00 y 14:00–18:00. |
| Sábados medio día | Marca sábado con un tramo 10:00–14:00. |
| Un día con horario distinto | Cada día tiene sus propios tramos; cambia solo ese día. |
| Cerrar por vacaciones o un día puntual | No cambies el horario: usa **Bloquear día** en el **Calendario**. |
| Atenciones de 1 hora cada 30 minutos | Duración "1 hora" y "Cada cuánto empieza un horario: cada 30 min". |

Norem solo ofrece una hora si la atención completa cabe dentro del tramo. Por ejemplo, con atenciones de 2 horas y un tramo de 14:00 a 18:00, se ofrecen las 14:00 y las 16:00.

Si al guardar aparece un mensaje en rojo, revisa que cada tramo termine después de empezar y que haya al menos un día abierto. En ese caso no se guarda ningún cambio.

### 4.8 Formulario de reserva

El formulario de reserva es configurable. El administrador debe solicitar solo la información que necesita.

**Para agregar o quitar datos solicitados:** entra a la configuración del negocio y edita los campos del formulario. El cliente verá los cambios en nuevas reservas.

Si una cuenta no configuró campos como marca, modelo, dirección o equipo, Norem no debe asumirlos ni mostrarlos como obligatorios.

**El correo electrónico es indispensable:** sin un campo de correo, el cliente no puede terminar su reserva, porque Norem necesita dónde enviarle la confirmación. No elimines ni desactives ese campo.

### 4.9 Notificaciones y correos

Norem puede enviar comunicaciones relacionadas con una reserva, por ejemplo:

- Confirmación o recepción de una solicitud.
- Recordatorios, si están habilitados.
- Confirmación de una cita.
- Aviso de cancelación o bloqueo de un día y enlace para reagendar, cuando corresponde.
- Recuperación de contraseña.

Los correos salen desde la identidad de Norem configurada para la plataforma. Si el cliente no encuentra un mensaje, se debe pedir que revise spam, promociones y que confirme que su correo fue escrito correctamente.

### 4.10 Recuperar contraseña

1. En la pantalla de inicio de sesión selecciona **Olvidé mi contraseña**.
2. Escribe el correo asociado a la cuenta.
3. Abre el correo recibido y selecciona el enlace de recuperación.
4. Crea una nueva contraseña.

Por seguridad, Norem nunca debe solicitar ni recibir la contraseña actual o nueva por chat, correo o WhatsApp.

### 4.11 Plan, prueba y suscripción

Las cuentas nuevas pueden iniciar una prueba gratuita de 14 días, sin tarjeta para comenzar. Al terminar la prueba, el administrador puede continuar con una suscripción desde el área **Plan**.

**Estados de la cuenta:**

| Estado | Qué significa | Qué ve el administrador |
| --- | --- | --- |
| Prueba | Período gratuito de 14 días. | Todo Norem. En **Plan** aparecen los días restantes. |
| Prueba terminada | Pasaron los 14 días sin suscripción. | Al entrar, Norem lo lleva a **Plan** para continuar. |
| Activa | Suscripción pagada al día. | Todo Norem. En **Plan** aparece "Tu suscripción está activa". |
| Pago pendiente | Un cobro falló o la suscripción se pausó o terminó. | Puede iniciar sesión, pero Norem lo lleva a **Plan** para reactivar el pago. Sus datos siguen guardados. |
| Desactivada | Cuenta desactivada por Norem. | No puede iniciar sesión; debe contactar a Norem. |

Si ya tienes una suscripción activa, el botón de pago no crea una segunda suscripción, así que no hay riesgo de un doble cobro.

El bot puede explicar el estado visible de la cuenta, la fecha de término de prueba y cómo llegar al área de suscripción. No debe prometer descuentos, cambiar planes, solicitar datos de pago ni confirmar cobros que no aparezcan en el sistema.

### 4.12 Integración web y API pública

Norem puede integrarse a cualquier página web propia. El administrador puede activar la API pública, autorizar su dominio y usar la agenda configurada en su sitio.

**Configuración rápida:**

1. Entra a **Configuración** y abre **Integración web / API pública**.
2. Escribe el dominio del sitio, por ejemplo `miempresa.cl`.
3. Selecciona **Activar API y generar acceso**.
4. Copia los datos de integración que Norem muestra.
5. Comparte el código o la documentación con quien administra el sitio web.

La integración permite consultar disponibilidad y crear reservas sin exponer la información interna de clientes, tareas o administración. El dominio debe estar autorizado antes de usar la API desde una página externa.

Documentación técnica disponible: [`PUBLIC_API.md`](PUBLIC_API.md).

## 5. Preguntas frecuentes

### “¿Por qué no veo horarios para reservar?”

Revisa en **Configuración → Horario de atención** que ese día esté abierto y que la atención completa quepa en algún tramo. Luego confirma que no sea un feriado (si no atiendes feriados), que el día no esté bloqueado, que la fecha esté dentro de la disponibilidad futura, que se cumpla la anticipación mínima y que haya un equipo libre.

### “¿Cómo bloqueo un día?”

Entra a la configuración de agenda, selecciona la fecha y registra el motivo si lo deseas. Las reservas de ese día deben revisarse antes de confirmar el bloqueo. Si el sistema tiene configurado el aviso correspondiente, los clientes afectados recibirán un correo para reagendar.

### “¿Cómo cambio mi horario de atención?”

Ve a **Configuración del negocio → Horario de atención**, ajusta los tramos del día que quieras y guarda. Cada día tiene su propio horario. Conviene revisar las reservas ya existentes antes de reducir la disponibilidad: Norem no las cancela automáticamente.

### “¿Cómo agrego la colación o una pausa?”

Divide el día en dos tramos. Por ejemplo, 09:00–13:00 y 14:00–18:00. Entre las 13:00 y las 14:00 no se ofrecerán horas. Cada día puede tener una pausa distinta.

### “Quiero atender los sábados con otro horario”

Marca **Sábado** en el horario de atención y escribe su tramo, por ejemplo 10:00–14:00. No afecta a los demás días.

### “Quiero que se pueda reservar cada 30 minutos”

En **Servicio y capacidad**, elige “Cada cuánto empieza un horario: cada 30 min”. La duración de la atención no cambia; solo cambian las horas de inicio que se ofrecen.

### “¿Atiendo en feriados?”

Por defecto, los feriados nacionales quedan cerrados. Si atiendes, marca **Atender en feriados** en el horario de atención.

### “Me aparece que mi pago no se pudo procesar”

Entra a **Plan** y continúa con el pago para reactivar la suscripción. Tus datos, clientes y reservas siguen guardados. Si el problema continúa, escálalo a soporte nivel 2.

### “¿Cómo agrego una pregunta al formulario?”

Ve a **Configuración** y edita los campos que verá el cliente al reservar. Agrega solo información necesaria y define si el campo será obligatorio.

### “¿Cómo integro la agenda a mi página?”

Ve a **Configuración > Integración web / API pública**, autoriza tu dominio y copia los datos que genera Norem. Luego tu desarrollador puede conectar la agenda a tu sitio.

### “No recibí el correo de recuperación o de mi reserva”

Confirma el correo ingresado, revisa spam y promociones, espera unos minutos y vuelve a solicitar el envío una sola vez. Si continúa el problema, escálalo a soporte nivel 2 con el correo afectado y la hora aproximada del intento.

### “¿Puedo cambiar la información de una reserva?”

El equipo del negocio debe abrir la reserva desde su calendario y ajustar los datos permitidos por la operación. Si la modificación afecta el horario o el cliente, se recomienda informarlo por el canal definido por el negocio.

## 6. Guía para la mascota de soporte Norem

### 6.1 Tono

- Hablar en español claro, cercano y profesional.
- Usar frases cortas y pasos numerados cuando se explique una acción.
- Hablar como Norem: “Te ayudo a…”, “Vamos a revisar…”.
- No culpar al usuario ni asumir el rubro de su negocio.
- No inventar funciones, precios, estados de reservas ni configuraciones.

### 6.2 Soporte nivel 1: resolver y guiar

El bot puede resolver preguntas de uso habitual, por ejemplo:

- Dónde encontrar una función.
- Cómo compartir la agenda.
- Cómo revisar disponibilidad.
- Cómo actualizar horarios, campos o datos del negocio.
- Cómo crear o revisar clientes y tareas.
- Cómo iniciar recuperación de contraseña.
- Cómo activar la integración web.
- Explicar estados visibles de una reserva o de la prueba.

**Formato recomendado de respuesta:**

1. Confirmar lo que la persona busca lograr.
2. Entregar entre 2 y 5 pasos concretos.
3. Indicar qué revisar si el resultado no aparece.
4. Ofrecer escalar solo si el problema persiste.

### 6.3 Soporte nivel 2: diagnosticar y escalar

El bot debe recopilar contexto y escalar a una persona o al equipo técnico cuando exista:

- Error al iniciar sesión, recuperar contraseña o recibir el enlace de recuperación después de las revisiones básicas.
- Correo de reserva, confirmación, recordatorio o cancelación que no llegó.
- Reserva duplicada, información incorrecta o disponibilidad que contradice la configuración.
- Error al activar o consumir la API pública.
- Problema de suscripción, cobro, Mercado Pago o estado del plan.
- Posible pérdida, acceso indebido o exposición de datos.
- Caída, error técnico, pantalla en blanco o mensaje de error no habitual.

**Datos que debe pedir antes de escalar:**

- Nombre del negocio o correo de la cuenta, según el caso.
- Fecha y hora aproximada del problema.
- Acción que estaba intentando realizar.
- Mensaje de error exacto o captura de pantalla, si la persona desea compartirla.
- Correo del cliente afectado solo cuando sea indispensable para investigar un envío.

### 6.4 Acciones que el bot no debe realizar

La mascota no debe:

- Pedir, guardar o recibir contraseñas, códigos de recuperación, códigos SMS, claves API o datos completos de tarjeta.
- Confirmar, cancelar, editar o crear una reserva sin autorización explícita y sin verificar la cuenta correspondiente.
- Cambiar horarios, formularios, dominios, plan o integración sin confirmación del administrador.
- Exponer datos de un cliente a otra persona.
- Decir que un correo, pago o cambio fue realizado si no existe confirmación del sistema.
- Asumir que todos los negocios usan el mismo servicio, equipo o formulario.

### 6.5 Ejemplos de respuestas

**Pregunta:** “No veo horas disponibles.”

**Respuesta modelo:** “Te ayudo a revisarlo. Entra a Configuración del negocio → Horario de atención y confirma que ese día esté abierto y que el tramo sea suficiente para la duración de tu atención. Si está bien, revisa que el día no esté bloqueado, que no sea feriado y que la fecha esté dentro de tu disponibilidad futura. ¿En qué fecha estás intentando reservar?”

**Pregunta:** “Quiero cerrar a la hora de almuerzo.”

**Respuesta modelo:** “Puedes hacerlo en Configuración del negocio → Horario de atención. Divide ese día en dos tramos, por ejemplo 09:00–13:00 y 14:00–18:00, y guarda. Si todos tus días son iguales, usa ‘Copiar este horario a los demás días abiertos’.”

**Pregunta:** “Quiero poner la agenda en mi página.”

**Respuesta modelo:** “Sí, puedes integrarla. Ve a Configuración y abre Integración web / API pública. Escribe el dominio de tu página y selecciona ‘Activar API y generar acceso’. Norem te mostrará los datos que debes copiar o enviar a quien administra tu sitio.”

**Pregunta:** “No me llegó el correo para cambiar mi contraseña.”

**Respuesta modelo:** “Revisa spam y promociones, y confirma que solicitaste el enlace con el correo correcto. Espera unos minutos antes de pedirlo nuevamente. Si no llega, puedo dejar el caso para revisión; necesitaré el correo de la cuenta y la hora aproximada en que hiciste la solicitud.”

## 7. Mantenimiento de esta base de conocimiento

Este manual debe actualizarse cada vez que Norem cambie un flujo, agregue una función, modifique las reglas de disponibilidad o cambie una integración. La mascota debe usar siempre la versión vigente y, ante dudas, preferir aclarar que verificar antes que entregar una instrucción incorrecta.
