# Entrega de correos Norem

## Arquitectura actual

Vercel ejecuta la aplicación Norem. No envía correos por sí mismo: abre una conexión cifrada al relay SMTP configurado en `SMTP_HOST`, se autentica con `EMAIL_SENDER` y `EMAIL_PASSWORD`, y ese servidor (normalmente el hosting/cPanel) entrega el mensaje a Gmail.

En producción deben existir explícitamente estas variables en Vercel:

```text
EMAIL_SENDER
EMAIL_PASSWORD
SMTP_HOST
SMTP_PORT=465
SMTP_TIMEOUT_SECONDS=15
EMAIL_REPLY_TO
```

Norem registra solamente estados técnicos sin correos, claves ni tokens:

- `smtp_message_accepted`: el relay aceptó el destinatario.
- `smtp_recipient_rejected`: el relay rechazó al destinatario.
- `smtp_message_failed`: falló conexión, TLS o autenticación.

La aceptación por SMTP confirma que el hosting recibió el mensaje; la entrega final la decide Gmail según autenticación y reputación.

## Validación en cPanel y Gmail

1. En cPanel abre **Email Deliverability** y confirma que DKIM y SPF figuren como reparados para `norem.cl`.
2. Envía un restablecimiento a una cuenta Gmail de prueba.
3. En Gmail abre el mensaje, selecciona **Mostrar original** y comprueba: `SPF: PASS`, `DKIM: PASS` y `DMARC: PASS`.
4. Añade `norem.cl` a Google Postmaster Tools para medir reputación, spam y errores de entrega.

No es posible garantizar la bandeja de entrada para cada destinatario: Gmail toma la decisión final. Si SPF/DKIM/DMARC pasan y los mensajes continúan en Spam, se debe usar un proveedor transaccional con reputación administrada (por ejemplo, Postmark Transactional) y un subdominio exclusivo como `notify.norem.cl`.
