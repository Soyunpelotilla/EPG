#!/usr/bin/env python3
# ==============================================================================
# Script: scraper_epg.py
# Función: Raspa programación de gatotv.com y genera XML en formato XMLTV
# ==============================================================================

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
from xml.dom import minidom
import time
import re

# ==============================================================================
# CONFIGURACIÓN - Añade o quita canales aquí
# ==============================================================================

CANALES = [
    {
        "id": "fox_mexico",
        "nombre": "Canal Fox México",
        "url_slug": "fox_mexico",
        "logo": "https://imagenes.gatotv.com/logos/canales/oscuros/fox-mediano.png",
        "timezone_offset": "-0600"
    },
    {
        "id": "fox_plus_centroamerica",
        "nombre": "FOX+ Centroamérica",
        "url_slug": "fox_plus_centroamerica",
        "logo": "https://imagenes.gatotv.com/logos/canales/oscuros/fox_plus-mediano.png",
        "timezone_offset": "-0600"
    },
    {
        "id": "5_mexico",
        "nombre": "Canal 5 México (XHGC)",
        "url_slug": "5_mexico",
        "logo": "https://imagenes.gatotv.com/logos/canales/oscuros/5_de_mexico-mediano.png",
        "timezone_offset": "-0600"
    },
]

# Cuántos días raspar (hoy + N días siguientes)
DIAS = 3

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "es-MX,es;q=0.9",
}

# ==============================================================================
# FUNCIONES
# ==============================================================================

def convertir_hora(hora_str, fecha, tz_offset):
    """
    Convierte '7:00 AM' o '10:30 PM' + fecha a formato XMLTV: '20261029070000 -0600'
    Maneja medianoche (12:00 AM) correctamente.
    """
    hora_str = hora_str.strip()
    try:
        t = datetime.strptime(hora_str, "%I:%M %p")
    except ValueError:
        try:
            t = datetime.strptime(hora_str, "%H:%M")
        except ValueError:
            return None

    dt = fecha.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
    return dt.strftime("%Y%m%d%H%M%S") + " " + tz_offset


def raspar_canal_dia(slug, fecha, tz_offset):
    """
    Raspa los programas de un canal para una fecha concreta.
    Devuelve lista de dicts: {titulo, inicio, fin}
    """
    fecha_str = fecha.strftime("%Y-%m-%d")
    url = f"https://www.gatotv.com/canal/{slug}/{fecha_str}"

    print(f"  → Raspando: {url}")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"  ✗ Error al descargar {url}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    programas = []

    # La tabla de programación tiene filas con hora inicio, hora fin, programa
    tabla = soup.find("table")
    if not tabla:
        print(f"  ✗ No se encontró tabla en {url}")
        return []

    filas = tabla.find_all("tr")
    for fila in filas:
        celdas = fila.find_all("td")
        if len(celdas) < 3:
            continue

        hora_inicio_txt = celdas[0].get_text(strip=True)
        hora_fin_txt = celdas[1].get_text(strip=True)

        # La celda del programa puede tener texto simple o enlace
        celda_prog = celdas[2]
        # Primero intentamos obtener el título del enlace o texto directo
        titulo = celda_prog.get_text(separator="\n", strip=True).split("\n")[0].strip()

        # Saltar filas de cabecera o secciones (Madrugada, Mañana, etc.)
        if not hora_inicio_txt or not re.search(r"AM|PM|:", hora_inicio_txt):
            continue
        if not titulo or titulo in ["Hora Inicio", "Programa", ""]:
            continue

        # Convertir horas
        # Si hora_fin es "12:00 AM" y hora_inicio es noche → el fin es el día siguiente
        inicio_dt = convertir_hora(hora_inicio_txt, fecha, tz_offset)

        # Para la hora fin: si empieza en PM y termina en AM → sumar un día
        fin_fecha = fecha
        if re.search(r"PM", hora_inicio_txt) and re.search(r"AM", hora_fin_txt):
            fin_fecha = fecha + timedelta(days=1)
        fin_dt = convertir_hora(hora_fin_txt, fin_fecha, tz_offset)

        if inicio_dt and fin_dt and titulo:
            programas.append({
                "titulo": titulo,
                "inicio": inicio_dt,
                "fin": fin_dt,
            })

    print(f"  ✓ {len(programas)} programas encontrados para {fecha_str}")
    return programas


def generar_xml(canales_data):
    """
    Genera el XML en formato XMLTV a partir de los datos raspados.
    """
    tv = ET.Element("tv")
    tv.set("generator-info-name", "scraper_epg.py")
    tv.set("generator-info-url", "https://github.com")

    # 1. Escribir canales
    for canal in canales_data:
        ch = ET.SubElement(tv, "channel")
        ch.set("id", canal["id"])
        dn = ET.SubElement(ch, "display-name")
        dn.text = canal["nombre"]
        if canal.get("logo"):
            icon = ET.SubElement(ch, "icon")
            icon.set("src", canal["logo"])

    # 2. Escribir programas
    for canal in canales_data:
        for prog in canal["programas"]:
            programme = ET.SubElement(tv, "programme")
            programme.set("start", prog["inicio"])
            programme.set("stop", prog["fin"])
            programme.set("channel", canal["id"])
            titulo_el = ET.SubElement(programme, "title")
            titulo_el.set("lang", "es")
            titulo_el.text = prog["titulo"]

    # Formatear XML bonito
    xml_str = ET.tostring(tv, encoding="unicode")
    dom = minidom.parseString(xml_str)
    return dom.toprettyxml(indent="  ", encoding="UTF-8").decode("UTF-8")


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    print("═══ INICIANDO SCRAPER EPG GATOTV ═══")
    hoy = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    fechas = [hoy + timedelta(days=i) for i in range(DIAS)]

    canales_data = []

    for canal in CANALES:
        print(f"\n─── Canal: {canal['nombre']} ───")
        todos_programas = []

        for fecha in fechas:
            programas_dia = raspar_canal_dia(
                canal["url_slug"], fecha, canal["timezone_offset"]
            )
            todos_programas.extend(programas_dia)
            time.sleep(1)  # Pausa entre peticiones para no saturar el servidor

        canales_data.append({
            "id": canal["id"],
            "nombre": canal["nombre"],
            "logo": canal["logo"],
            "programas": todos_programas,
        })

        total = len(todos_programas)
        print(f"  ═► Total {canal['nombre']}: {total} programas en {DIAS} días")

    print("\n─── GENERANDO XML ───")
    xml_output = generar_xml(canales_data)

    with open("guide.xml", "w", encoding="UTF-8") as f:
        f.write(xml_output)

    # Contar totales
    total_programas = sum(len(c["programas"]) for c in canales_data)
    print(f"✓ guide.xml generado correctamente")
    print(f"  Canales: {len(canales_data)} | Programas: {total_programas}")
    print("═══ PROCESO FINALIZADO ═══")


if __name__ == "__main__":
    main()
