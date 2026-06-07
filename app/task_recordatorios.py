from datetime import timedelta
from app.database import SessionLocal
from app.models import Agendamiento, get_now_chile
from app.utils.email_utils import enviar_email_base
def enviar_correo_recordatorio(cliente_email, nombre, fecha, hora, patente):
    """Envía el recordatorio de cita para el día siguiente. Reutiliza enviar_email_base."""
    asunto = f"⏰ Recordatorio: Tu mantención es mañana ({patente})"

    html = f"""
    <html>
        <body style="margin:0; padding:0; background-color:#f4f7f6; font-family: 'Segoe UI', Arial, sans-serif;">
            <table width="100%" border="0" cellspacing="0" cellpadding="0" style="padding: 40px 0;">
                <tr>
                    <td align="center">
                        <table width="500" border="0" cellspacing="0" cellpadding="0" style="background-color:#ffffff; border-radius:15px; overflow:hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
                            <tr>
                                <td align="center" style="padding: 30px 0 10px 0;">
                                    <div style="display: inline-block; width: 60px; height: 60px; line-height: 60px; border-radius: 50%; background-color: #fef9c3; color: #f59e0b; font-size: 32px; text-align: center;">⏰</div>
                                    <h2 style="color:#1e293b; margin: 8px 0 4px 0;">LOCAL</h2>
                                    <p style="color:#64748b; font-size:12px; margin:0; text-transform: uppercase;">Sistema de Agendamiento</p>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 30px 40px 40px 40px; text-align: center;">
                                    <h3 style="color:#1e293b; font-size:20px; margin-bottom:10px;">¡Tu cita es mañana!</h3>
                                    <p style="color:#475569; font-size:16px;">Hola <strong>{nombre}</strong>, te recordamos que tienes una mantención agendada:</p>
                                    <div style="background-color:#f8fafc; border-radius:10px; padding:20px; margin:20px 0; text-align:left;">
                                        <p style="margin:5px 0; color:#1e293b;">📅 <strong>Fecha:</strong> {fecha}</p>
                                        <p style="margin:5px 0; color:#1e293b;">🕒 <strong>Hora:</strong> {hora} hrs</p>
                                        <p style="margin:5px 0; color:#1e293b;">🚗 <strong>Vehículo:</strong> {patente}</p>
                                    </div>
                                    <p style="color:#64748b; font-size:13px; margin-top:20px;">Si tienes algún inconveniente, por favor contáctanos respondiendo este correo.</p>
                                </td>
                            </tr>
                            <tr>
                                <td style="background-color:#f8fafc; padding:20px; text-align:center; color:#94a3b8; font-size:11px;">
                                    Este es un mensaje automático del Sistema de Agendamiento.
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
    </html>
    """

    return enviar_email_base(cliente_email, asunto, html)

def procesar_agendamientos_manana():
    db = SessionLocal()
    try:
        # Usamos get_now_chile() para zona horaria correcta (America/Santiago)
        manana = get_now_chile() + timedelta(days=1)
        inicio_manana = manana.replace(hour=0, minute=0, second=0, microsecond=0)
        fin_manana = manana.replace(hour=23, minute=59, second=59, microsecond=999)

        # Buscamos citas para mañana que no estén canceladas
        citas = db.query(Agendamiento).filter(
            Agendamiento.fecha_inicio >= inicio_manana,
            Agendamiento.fecha_inicio <= fin_manana,
            Agendamiento.estado != "cancelado"
        ).all()

        print(f"[{get_now_chile()}] Revisando recordatorios... Encontrados: {len(citas)}")

        for cita in citas:
            fecha_str = cita.fecha_inicio.strftime('%d-%m-%Y')
            hora_str = cita.fecha_inicio.strftime('%H:%M')
            
            exito = enviar_correo_recordatorio(
                cita.correo, 
                cita.nombre, 
                fecha_str, 
                hora_str, 
                cita.patente
            )
            if exito:
                print(f"✅ Recordatorio enviado a {cita.correo} para la cita de las {hora_str}")

    finally:
        db.close()

if __name__ == "__main__":
    procesar_agendamientos_manana()