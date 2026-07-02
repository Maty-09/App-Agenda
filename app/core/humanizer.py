import asyncio

async def simular_tipeo(texto: str) -> None:
    """
    Simula el tiempo que tardaría un humano en escribir un mensaje.
    Calcula un retraso basado en la longitud del texto (0.05 seg por palabra),
    con un tope máximo de 2.5 segundos.
    """
    palabras = texto.split()
    cantidad_palabras = len(palabras)
    
    # 0.05 segundos por palabra
    retraso = cantidad_palabras * 0.05
    
    # Tope máximo de 2.5 segundos
    retraso_final = min(retraso, 2.5)
    
    # Simular la espera de forma asíncrona (no bloquea el servidor)
    await asyncio.sleep(retraso_final)
