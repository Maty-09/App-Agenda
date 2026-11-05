"""Horario de atención configurable por cada negocio (tenant).

Fuente única de verdad para saber qué días y en qué tramos atiende un negocio.
Cada día de la semana (0 = lunes … 6 = domingo) tiene cero o más tramos
``[inicio, fin]`` en formato "HH:MM"; un día sin tramos está cerrado. Las
pausas (colación, etc.) se expresan simplemente como dos tramos separados.

Formato guardado en ``config_json["reglas_negocio"]``::

    "horario_semanal": {"0": [["09:00", "13:00"], ["14:00", "18:00"]], "5": [["10:00", "14:00"]]},
    "intervalo_minutos": 30,      # opcional: cada cuánto empieza un horario
    "atiende_feriados": false     # opcional

Configuraciones antiguas (``dias_habiles`` + ``bloques_horarios`` + ``pausa``)
se siguen leyendo y se convierten a este formato.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import holidays

DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
# Horas de inicio usadas por las agendas antiguas que nunca guardaron un horario.
_INICIOS_LEGACY = ["09:00", "13:00", "15:30"]
_feriados_cl = holidays.country_holidays("CL")


def _minutos(hhmm: str) -> int:
    hora, minuto = str(hhmm).strip().split(":")
    hora, minuto = int(hora), int(minuto)
    if not (0 <= hora <= 24 and 0 <= minuto < 60) or (hora == 24 and minuto):
        raise ValueError(f"Hora inválida: {hhmm}")
    return hora * 60 + minuto


def _hhmm(minutos: int) -> str:
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def reglas(config: dict | None) -> dict:
    valor = (config or {}).get("reglas_negocio", {})
    return valor if isinstance(valor, dict) else {}


def duracion_minutos(config: dict | None, por_defecto: int = 60) -> int:
    try:
        minutos = int((config or {}).get("negocio", {}).get("duracion_minutos", por_defecto))
    except (TypeError, ValueError):
        minutos = por_defecto
    return max(15, min(480, minutos))


def normalizar_tramos(tramos) -> list[tuple[int, int]]:
    """Valida, ordena y une tramos; descarta los inválidos."""
    limpios = []
    for tramo in tramos or []:
        try:
            inicio, fin = (_minutos(valor) for valor in tramo)
        except (TypeError, ValueError):
            continue
        if inicio < fin:
            limpios.append((inicio, fin))
    limpios.sort()
    unidos: list[tuple[int, int]] = []
    for inicio, fin in limpios:
        if unidos and inicio <= unidos[-1][1]:
            unidos[-1] = (unidos[-1][0], max(unidos[-1][1], fin))
        else:
            unidos.append((inicio, fin))
    return unidos


def _horario_legacy(r: dict, duracion: int) -> dict[int, list[tuple[int, int]]]:
    try:
        dias = {int(dia) for dia in r.get("dias_habiles", [0, 1, 2, 3, 4])}
    except (TypeError, ValueError):
        dias = {0, 1, 2, 3, 4}
    bloques = r.get("bloques_horarios", {}) if isinstance(r.get("bloques_horarios"), dict) else {}
    pausa = normalizar_tramos([r.get("pausa")]) if r.get("pausa") else []
    horario: dict[int, list[tuple[int, int]]] = {}
    for dia in range(7):
        if dia not in dias:
            continue
        lista = bloques.get(str(dia), _INICIOS_LEGACY)
        try:
            es_rango = len(lista) == 2 and _minutos(lista[0]) < _minutos(lista[1])
        except (TypeError, ValueError):
            es_rango = False
        if es_rango and lista is not _INICIOS_LEGACY:
            # Formato del onboarding: [inicio, término] de la jornada, con pausa opcional.
            inicio, fin = _minutos(lista[0]), _minutos(lista[1])
            tramos = [(inicio, fin)]
            if pausa:
                p_inicio, p_fin = pausa[0]
                if inicio < p_fin and p_inicio < fin:
                    tramos = [t for t in ((inicio, min(p_inicio, fin)), (max(p_fin, inicio), fin)) if t[0] < t[1]]
        else:
            # Formato antiguo: lista de horas de inicio fijas. Cada una se
            # convierte en un tramo del largo de la atención.
            tramos = []
            for valor in lista:
                try:
                    inicio = _minutos(valor)
                except (TypeError, ValueError):
                    continue
                tramos.append((inicio, min(inicio + duracion, 24 * 60)))
        horario[dia] = normalizar_tramos([(_hhmm(a), _hhmm(b)) for a, b in tramos])
    return horario


def horario_semanal(config: dict | None) -> dict[int, list[tuple[int, int]]]:
    """Tramos (en minutos desde medianoche) por día de la semana."""
    r = reglas(config)
    guardado = r.get("horario_semanal")
    if isinstance(guardado, dict):
        return {dia: normalizar_tramos(guardado.get(str(dia), [])) for dia in range(7)}
    legacy = _horario_legacy(r, duracion_minutos(config))
    return {dia: legacy.get(dia, []) for dia in range(7)}


def horario_semanal_texto(config: dict | None) -> dict[str, list[list[str]]]:
    """Mismo horario en formato serializable ("HH:MM") para plantillas y APIs."""
    return {
        str(dia): [[_hhmm(a), _hhmm(b)] for a, b in tramos]
        for dia, tramos in horario_semanal(config).items()
    }


def dias_abiertos(config: dict | None) -> set[int]:
    return {dia for dia, tramos in horario_semanal(config).items() if tramos}


def intervalo_minutos(config: dict | None, duracion: int) -> int:
    try:
        valor = int(reglas(config).get("intervalo_minutos") or duracion)
    except (TypeError, ValueError):
        valor = duracion
    return max(5, min(480, valor))


def atiende_feriados(config: dict | None) -> bool:
    return bool(reglas(config).get("atiende_feriados", False))


def es_feriado(fecha: date) -> bool:
    return fecha in _feriados_cl


def nombre_feriado(fecha: date) -> str | None:
    return _feriados_cl.get(fecha)


def cerrado_por_feriado(config: dict | None, fecha: date) -> bool:
    return es_feriado(fecha) and not atiende_feriados(config)


def inicios_del_dia(config: dict | None, dia_semana: int, duracion: int | float | None = None) -> list[str]:
    """Horas de inicio ofrecidas un día de la semana.

    `duracion` en minutos; por defecto la del negocio. Un horario se ofrece si
    la atención completa cabe dentro de un tramo.
    """
    duracion = int(round(duracion)) if duracion else duracion_minutos(config)
    paso = intervalo_minutos(config, duracion)
    salida = []
    for inicio, fin in horario_semanal(config).get(dia_semana, []):
        actual = inicio
        while actual + duracion <= fin:
            salida.append(_hhmm(actual))
            actual += paso
    return salida


def cabe_en_horario(config: dict | None, inicio: datetime, fin: datetime) -> bool:
    """True si [inicio, fin) cae completo dentro de un tramo de ese día."""
    if fin.date() != inicio.date() and not (fin.date() == inicio.date() + timedelta(days=1) and fin.hour == 0 and fin.minute == 0):
        return False
    a = inicio.hour * 60 + inicio.minute
    b = a + int((fin - inicio).total_seconds() // 60)
    return any(t_inicio <= a and b <= t_fin for t_inicio, t_fin in horario_semanal(config).get(inicio.weekday(), []))


def describir_horario(config: dict | None, dia_semana: int) -> str:
    tramos = horario_semanal(config).get(dia_semana, [])
    if not tramos:
        return "Cerrado"
    return ", ".join(f"{_hhmm(a)}–{_hhmm(b)}" for a, b in tramos)


def parsear_formulario(form) -> tuple[dict[str, list[list[str]]], list[str]]:
    """Lee el editor semanal del panel. Devuelve (horario, errores).

    Espera, por día `d`: `dia_{d}_abierto=1` y listas `tramo_{d}_inicio` /
    `tramo_{d}_fin` (una entrada por tramo).
    """
    horario: dict[str, list[list[str]]] = {}
    errores: list[str] = []
    for dia in range(7):
        if form.get(f"dia_{dia}_abierto") != "1":
            horario[str(dia)] = []
            continue
        inicios = form.getlist(f"tramo_{dia}_inicio")
        fines = form.getlist(f"tramo_{dia}_fin")
        crudos = []
        for inicio, fin in zip(inicios, fines):
            if not inicio and not fin:
                continue
            try:
                if _minutos(inicio) >= _minutos(fin):
                    errores.append(f"{DIAS_SEMANA[dia]}: el tramo {inicio}–{fin} debe terminar después de empezar.")
                    continue
            except (TypeError, ValueError):
                errores.append(f"{DIAS_SEMANA[dia]}: revisa las horas del tramo.")
                continue
            crudos.append((inicio, fin))
        tramos = normalizar_tramos(crudos)
        if not tramos and not errores:
            errores.append(f"{DIAS_SEMANA[dia]} está marcado como abierto pero no tiene horario.")
        horario[str(dia)] = [[_hhmm(a), _hhmm(b)] for a, b in tramos]
    if not errores and not any(horario.values()):
        errores.append("Debes abrir al menos un día de la semana.")
    return horario, errores
