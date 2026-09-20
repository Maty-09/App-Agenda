# Plan de implementación: DTE chilenos en Norem

**Estado:** Fase 0 - diseño e inspección.  
**Fecha de revisión:** 2026-09-20.  
**Estado de emisión:** no habilitada. La única implementación inicial permitida será `mock`.

## Propósito y límite del módulo

Norem incorporará un módulo de documentos tributarios electrónicos (DTE) para que cada empresa cliente pueda operar con su propio RUT emisor, receptores, folios, artefactos y configuración. El contribuyente seguirá siendo el emisor y responsable tributario; Norem es una plataforma tecnológica y no sustituye al contador, asesor legal, proveedor DTE ni al SII.

El primer alcance funcional previsto es factura electrónica afecta, factura exenta/no afecta, boleta afecta y boleta exenta/no afecta. Notas de crédito y débito se modelarán desde el inicio como documentos relacionados, pero no se emitirán en la primera entrega.

No se implementará una integración directa con SII ni se habilitará producción hasta contar con proveedor o canal de firma seleccionado, documentación vigente, ambiente de certificación y aprobaciones requeridas.

## Arquitectura encontrada

| Área | Hallazgo | Consecuencia para DTE |
| --- | --- | --- |
| Aplicación | FastAPI con Python, plantillas Jinja y API REST; punto de entrada en `app/main.py`. | El módulo se integrará como contexto aislado, sin reescribir agenda ni autenticación. |
| Producción | Vercel, runtime Python 3.12 (`vercel.json`). | No usar filesystem local ni tareas en memoria para emisión o custodia. |
| Datos | SQLAlchemy y PostgreSQL mediante `DATABASE_URL`; Alembic en `alembic/`. | Todas las tablas DTE se crearán con migraciones reversibles, nunca con `create_all`. |
| Empresas | `Tenant` representa la organización en `app/core/models.py`; entidades operacionales usan `tenant_id`. | Todo dato DTE debe estar aislado por tenant y emisor. |
| Identidad | JWT en cookie contiene usuario, rol y tenant. `verificar_login` revalida usuario, sesión y tenant. | Las rutas DTE resolverán el tenant desde sesión, no desde un ID recibido por navegador. |
| Negocio existente | Hay `Cliente` y `Agendamiento`, pero no catálogo de ítems, precios, pagos ni impuestos. | La agenda sólo será origen opcional de un borrador; no se emitirá automáticamente desde una reserva. |
| Suscripción Norem | Stripe/Mercado Pago facturan la suscripción SaaS de Norem. | Se mantiene estrictamente separado del DTE que emite cada cliente a sus propios receptores. |
| Procesamiento | APScheduler está deshabilitado en Vercel; sólo existe un cron acotado. | Antes de producción se requiere cola/worker durable o jobs externos idempotentes. |
| Secretos y archivos | Hay variables de entorno, pero no Secret Manager/KMS, almacenamiento de objetos ni URLs firmadas. | Es un bloqueo para firma y artefactos reales; se diseñarán abstracciones sin cargar certificados. |
| Pruebas | No se detectó una suite automatizada DTE. | La fase 1 incorpora pytest, fixtures de BD efímera y pruebas de seguridad críticas. |

## Principios no negociables

1. Norem no solicitará ni almacenará Clave Tributaria, contraseña PFX/P12, archivo PFX/P12, clave privada ni credenciales reutilizables en formularios, correo, tickets, frontend, logs ni la base transaccional.
2. Certificado y firma se tratarán mediante un proveedor formalmente habilitado o una zona aislada de firma/KMS validada. La aplicación de Norem nunca devolverá una clave privada al navegador.
3. Los documentos, CAF, folios, eventos y artefactos estarán segregados por `tenant_id` y por emisor. Un identificador conocido de otro tenant nunca dará acceso a XML, PDF ni estado.
4. El XML firmado será inmutable y será la fuente de verdad; PDF y representación visual serán derivados.
5. Después de un timeout de envío el estado será `UNKNOWN`; se reconciliará antes de cualquier reintento o nueva emisión.
6. Las reglas de IVA, exención, giro, receptor, correcciones y operación presencial serán configurables y requerirán validación de contador cuando corresponda.

## Arquitectura propuesta

Se creará un contexto aislado `app/domain_dte/` con validadores, esquemas, servicio de dominio, estado, auditoría, proveedores y rutas. Sus dependencias principales serán:

```text
UI / API de Norem
        |
        v
Servicio DTE (tenant + permiso + validación + idempotencia)
        |-----------------------------|
        v                             v
Motor de estados / auditoría     DteProvider (contrato interno)
        |                             |-- MockDteProvider (desarrollo)
        |                             |-- Adaptador proveedor elegido (futuro)
        |                             `-- sii_direct (futuro, no implementado)
        v
DocumentStorage / SecretProvider / SigningService
```

El contrato interno no dependerá de nombres, IDs o estados del proveedor:

```text
validate_configuration(input)
issue_document(input)
get_submission_status(input)
get_document_artifacts(input)
cancel_or_correct(input)
health_check(input)
```

Variables previstas, sin secretos en código:

```text
DTE_PROVIDER=mock
DTE_ENVIRONMENT=certification
```

`mock` generará resultados deterministas para pruebas y estará bloqueado para emitir documentos reales. Sólo un adaptador documentado y configurado podrá usar un proveedor real.

## Datos y migraciones previstas

Se incorporarán, en una fase posterior, las siguientes tablas con `tenant_id` e índices de aislamiento:

- `tax_emitters`: emisor, RUT, razón social, giro, dirección, ambiente, proveedor y estado.
- `tax_signers`: firmante, huella de certificado, vigencia y estado; sin clave privada.
- `dte_credentials`: proveedor, ambiente, referencia opaca a secreto, metadatos públicos y rotación.
- `dte_folio_ranges`: CAF cifrado/referenciado, tipo documental, rango y próximo folio.
- `dte_documents`: borrador, snapshots fiscales inmutables, totales calculados en backend, estados, correlaciones y referencias a artefactos.
- `dte_events`: auditoría append-only y saneada, sin XML ni secretos.
- `dte_delivery_attempts`: entrega de XML/PDF y sus intentos.
- `dte_document_relations`: relación con documentos correctivos para notas de crédito/débito futuras.

Restricciones centrales:

- Unicidad de `(tenant_id, emitter_id, document_type, folio)` cuando exista folio.
- Unicidad de `(tenant_id, emitter_id, idempotency_key)`.
- Misma clave de idempotencia con igual payload devuelve el mismo documento; con payload distinto se rechaza.
- La reserva de folio será transaccional y con lock en PostgreSQL. Un folio firmado o enviado no se reutiliza.

Los snapshots del receptor e ítems evitarán que cambios posteriores en `Cliente` o `Agendamiento` alteren un documento ya emitido.

## Permisos y operación

Los roles actuales son heterogéneos entre la interfaz HTML y la API, por lo que se agregarán permisos DTE independientes y compatibles: propietario/representante, administrador de facturación, emisor, aprobador, soporte de sólo lectura y auditor. El soporte requerirá acceso temporal, motivo y auditoría; nunca podrá ver secretos.

Las transiciones se controlarán mediante una máquina de estados. El ciclo principal incluye `DRAFT`, `VALIDATING`, `FOLIO_RESERVED`, `SIGNING`, `SIGNED`, `QUEUED`, `SUBMITTED`, `PROCESSING`, `ACCEPTED`, `REJECTED`, `UNKNOWN`, `FAILED_TRANSIENT` y `DEAD_LETTER`, además de estados separados de firma, transporte, resultado tributario y entrega.

Los jobs de envío, consulta, reconciliación, alertas de vencimiento/agote y entrega deberán ser idempotentes, con correlación, backoff, límite de intentos y cola de fallos. Vercel por sí solo no es suficiente para esa operación crítica.

## Archivos previstos

| Ruta | Acción posterior |
| --- | --- |
| `app/domain_dte/` | Nuevo contexto de dominio, validaciones, estados, proveedores y auditoría. |
| `app/api/routers/dte.py` | API autenticada DTE; tenant sólo desde la sesión. |
| `app/core/models.py` | Modelos SQLAlchemy DTE, en una fase con migración. |
| `alembic/versions/*_add_dte_domain.py` | Migración reversible, tras verificar `alembic current` y `alembic heads` de producción. |
| `app/infrastructure/dte_storage.py` | Abstracción de artefactos; sin filesystem persistente en producción. |
| `app/infrastructure/dte_jobs.py` | Contratos para worker/cron durable, sin APScheduler de proceso. |
| `templates/admin_dte_*.html` | Onboarding y emisión manual, después de las validaciones backend. |
| `tests/dte/` | Suite nueva de aislamiento, permisos, folios, idempotencia, webhooks y errores. |
| `docs/dte/02-*` a `09-*` | Arquitectura, onboarding, proveedor, estados, secretos, operación, checklist y preguntas regulatorias. |

## Plan por fases

### Fase 0 - decisiones y diseño (actual)

- Inspeccionar Norem y documentar riesgos.
- Elegir estrategia de proveedor y custodia de firma.
- Auditar estado real de migraciones de producción antes de una nueva revisión.
- Acordar alcance inicial, flujo de origen del documento y reglas tributarias con contador.

**Salida:** este documento. No hay emisión real.

### Fase 1 - base segura y mock

- Migraciones, modelos aislados, validación/normalización de RUT, permisos DTE y auditoría.
- Wizard de emisor que almacene únicamente datos tributarios no secretos y referencias opacas.
- `MockDteProvider`, folios simulados, idempotencia y pruebas de aislamiento/concurrencia.

**Salida:** borradores y simulación local/desarrollo, sin documentos válidos ante SII.

### Fase 2 - dominio de emisión

- Ítems, totales en backend, snapshots, validaciones, estados y reserva atómica de folio.
- Emisión manual de borrador desde cliente/agenda, sin automatismo desde una reserva.
- Abstracciones de almacenamiento y firma con bloqueo productivo explícito.

### Fase 3 - operación confiable

- Worker o cola durable, webhooks firmados y deduplicados, reconciliación, entrega, alertas, exportación y pruebas de resiliencia.

### Fase 4 - certificación del proveedor

- Adaptador del proveedor elegido solamente con contrato, documentación y credenciales válidas.
- Ambiente de certificación, casos exigidos y aprobación de contador/administrador por emisor.

### Fase 5 - producción gradual

- Activación explícita por emisor, piloto acotado, monitoreo y checklist.
- Notas de crédito/débito sólo después de estabilizar la emisión inicial.

## Riesgos y bloqueos actuales

1. **No hay proveedor DTE ni política de firma/custodia seleccionada.** Se recomienda un proveedor con API y soporte explícito multitenant para la primera versión, no integración SII directa.
2. **No hay Secret Manager/KMS, object storage cifrado ni worker durable.** Sin esos componentes no se habilita producción.
3. **No existen ítems, precios, pagos ni reglas tributarias en la agenda.** Se requiere formulario DTE propio y confirmación de contador; no inferir impuestos desde los campos existentes.
4. **Roles y dependencia API no son homogéneos.** DTE debe usar una dependencia estricta que revalide usuario, sesión, tenant y permiso.
5. **RLS existe sólo como script no conectado a las sesiones.** Las consultas y jobs DTE deberán filtrar tenant explícitamente y se evaluará RLS antes de confiar en ella.
6. **Normativa dinámica.** Las reglas de representación de boleta en la Resolución Exenta 12/2025 y eventuales modificaciones posteriores no se codificarán hasta validación con fuente SII vigente y contador; el índice oficial 2025 contiene resoluciones posteriores relacionadas con representación de boletas.

## Decisiones necesarias antes de Fase 4

1. Proveedor DTE elegido o lista corta para cotizar: soporte para boletas/facturas, onboarding de RUT por cliente, certificación, CAF, firma/custodia, webhooks, SLA, costos y exportación.
2. Modelo aceptado de firma/custodia: proveedor, HSM/KMS o componente local validado. Recomendación inicial: custodia/firma ofrecida formalmente por el proveedor.
3. Alcance comercial inicial: boleta de consumidor final, factura, ambos; y si el disparador será pago confirmado, cierre de servicio o acción manual.
4. Reglas por giro: afecto/exento/no afecto, servicios periódicos, sucursales, medios de pago, fecha de emisión y correcciones.
5. Infraestructura para artefactos cifrados, secretos y procesamiento durable.
6. Retención, exportación, privacidad y proceso de soporte con acceso temporal.

## Fuentes de verificación

- [Proceso de postulación y certificación de factura electrónica - SII](https://www.sii.cl/factura_electronica/factura_mercado/proc_postulacion.htm)
- [Certificado digital tributario - SII](https://www.sii.cl/destacados/factura_electronica/certificado_digital.htm)
- [Resolución Exenta SII N° 74 de 2020](https://www.sii.cl/normativa_legislacion/resoluciones/2020/reso74.pdf)
- [Formato DTE e información técnica vigente publicada por SII](https://www.sii.cl/factura_electronica/descripcion_formato.htm)
- [Formato XML DTE - SII](https://www.sii.cl/servicios_online/1039-formato_xml-1184.html)
- [Índice de resoluciones SII 2025, a revisar antes de cada implementación normativa](https://www.sii.cl/normativa_legislacion/resoluciones/2025/res_ind2025.htm)

## Criterio para continuar

La siguiente fase puede comenzar en modo mock seguro. Producción queda expresamente bloqueada hasta que el proveedor, la firma, el almacenamiento, el procesamiento durable y la certificación/aprobación aplicable estén resueltos y documentados.
