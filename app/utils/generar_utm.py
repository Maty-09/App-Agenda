def generar_utm(agendamiento):
    base_url = "/agendar_web"
    subtipo = agendamiento.subtipo.lower() if agendamiento.subtipo else ""
    subtipo_campaign = "local" if subtipo == "taller" else subtipo

    return (
        f"{base_url}?id={agendamiento.id}"
        f"&utm_source=web"
        f"&utm_medium={agendamiento.tipo_servicio}"
        f"&utm_campaign={subtipo_campaign}"
        f"&utm_term={agendamiento.equipo.replace(' ', '_')}"
        f"&utm_content={agendamiento.fecha_inicio.strftime('%Y%m%d')}"
    )