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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ==============================================================================
# FUNCIONES
# ==============================================================================

HORA_RE = re.compile(r"^\d{1,2}:\d{2}\s*(AM|PM)$", re.IGNORECASE)

def convertir_hora(hora_str, fecha, tz_offset):
    """Convierte '7:00 AM' + fecha a formato XMLTV '20261029070000 -0600'"""
    hora_str = hora_str.strip()
    try:
        t = datetime.strptime(hora_str, "%I:%M %p")
    except ValueError:
        return None
    dt = fecha.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
    return dt.strftime("%Y%m%d%H%M%S") + " " + tz_offset


def extraer_titulo_y_desc(celda):
    """
    Extrae título y descripción por separado de la celda del programa.
    El título es el texto del enlace o la primera línea.
    La descripción es el texto secundario si existe.
    """
    # Intentar obtener título del enlace <a>
    enlace = celda.find("a")
    if enlace:
        titulo = enlace.get_text(strip=True)
    else:
        # Sin enlace: primera línea del texto
        texto_completo = celda.get_text(separator="\n", strip=True)
        lineas = [l.strip() for l in texto_completo.split("\n") if l.strip()]
        titulo = lineas[0] if lineas else ""

    # Descripción: texto del párrafo o span adicional
    desc = ""
    for tag in celda.find_all(["p", "span", "small"]):
        t = tag.get_text(strip=True)
        if t and t != titulo:
            desc = t
            break

    # Si no hay desc por tag, buscar segunda línea del texto
    if not desc:
        texto_completo = celda.get_text(separator="\n", strip=True)
        lineas = [l.strip() for l in texto_completo.split("\n") if l.strip()]
        if len(lineas) > 1:
            # La segunda línea puede ser categoría o descripción
            segunda = lineas[1]
            # Si es muy corta probablemente es categoría (ej: "NFL"), la ignoramos
            if len(segunda) > 30:
                desc = segunda

    return titulo, desc


def raspar_canal_dia(slug, fecha, tz_offset):
    """Raspa los programas de un canal para una fecha concreta."""
    fecha_str = fecha.strftime("%Y-%m-%d")
    url = f"https://www.gatotv.com/canal/{slug}/{fecha_str}"
    print(f"  → Raspando: {url}")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    programas = []
    vistos = set()  # Para deduplicar dentro del mismo día

    for tabla in soup.find_all("table"):
        for fila in tabla.find_all("tr"):
            celdas = fila.find_all("td")

            # Extraer textos no vacíos
            textos = [c.get_text(separator=" ", strip=True) for c in celdas]
            textos = [t for t in textos if t]

            if len(textos) < 3:
                continue

            hora_inicio_txt = textos[0]
            hora_fin_txt = textos[1]

            if not HORA_RE.match(hora_inicio_txt):
                continue
            if not HORA_RE.match(hora_fin_txt):
                continue

            # Extraer título y descripción de la celda correcta
            celda_prog = None
            idx = 0
            for c in celdas:
                if c.get_text(strip=True) == hora_inicio_txt:
                    idx = list(celdas).index(c)
                    break
            # La celda del programa es la que viene después de hora_fin
            celdas_con_texto = [c for c in celdas if c.get_text(strip=True)]
            if len(celdas_con_texto) >= 3:
                celda_prog = celdas_con_texto[2]
            else:
                continue

            titulo, desc = extraer_titulo_y_desc(celda_prog)

            if not titulo:
                continue

            # Calcular fecha de fin
            fin_fecha = fecha
            if re.search(r"PM", hora_inicio_txt, re.I) and re.search(r"AM", hora_fin_txt, re.I):
                fin_fecha = fecha + timedelta(days=1)

            inicio_dt = convertir_hora(hora_inicio_txt, fecha, tz_offset)
            fin_dt = convertir_hora(hora_fin_txt, fin_fecha, tz_offset)

            if not inicio_dt or not fin_dt:
                continue

            # Deduplicar por clave inicio+titulo
            clave = f"{inicio_dt}|{titulo}"
            if clave in vistos:
                continue
            vistos.add(clave)

            programas.append({
                "titulo": titulo,
                "desc": desc,
                "inicio": inicio_dt,
                "fin": fin_dt,
            })

    print(f"  ✓ {len(programas)} programas para {fecha_str}")
    return programas


def generar_xml(canales_data):
    """Genera el XML en formato XMLTV."""
    tv = ET.Element("tv")
    tv.set("generator-info-name", "scraper_epg.py")
    tv.set("generator-info-url", "https://github.com")

    # Canales
    for canal in canales_data:
        ch = ET.SubElement(tv, "channel")
        ch.set("id", canal["id"])
        dn = ET.SubElement(ch, "display-name")
        dn.text = canal["nombre"]
        if canal.get("logo"):
            icon = ET.SubElement(ch, "icon")
            icon.set("src", canal["logo"])

    # Programas
    for canal in canales_data:
        for prog in canal["programas"]:
            programme = ET.SubElement(tv, "programme")
            programme.set("start", prog["inicio"])
            programme.set("stop", prog["fin"])
            programme.set("channel", canal["id"])
            titulo_el = ET.SubElement(programme, "title")
            titulo_el.set("lang", "es")
            titulo_el.text = prog["titulo"]
            if prog.get("desc"):
                desc_el = ET.SubElement(programme, "desc")
                desc_el.set("lang", "es")
                desc_el.text = prog["desc"]

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
            programas_dia = raspar_canal_dia(canal["url_slug"], fecha, canal["timezone_offset"])
            todos_programas.extend(programas_dia)
            time.sleep(1.5)

        canales_data.append({
            "id": canal["id"],
            "nombre": canal["nombre"],
            "logo": canal["logo"],
            "programas": todos_programas,
        })
        print(f"  ═► Total: {len(todos_programas)} programas en {DIAS} días")

    print("\n─── GENERANDO XML ───")
    xml_output = generar_xml(canales_data)

    with open("guide.xml", "w", encoding="UTF-8") as f:
        f.write(xml_output)

    total = sum(len(c["programas"]) for c in canales_data)
    print(f"✓ guide.xml generado — Canales: {len(canales_data)} | Programas: {total}")
    print("═══ PROCESO FINALIZADO ═══")


if __name__ == "__main__":
    main()
