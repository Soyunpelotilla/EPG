#!/usr/bin/env python3
# ==============================================================================
# Script: scraper_epg.py - V2 FIX
# Fix: usa ZoneInfo para México -> España, corrige hueco 00:00-08:00
# ==============================================================================

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
from xml.dom import minidom
import time
import re
from zoneinfo import ZoneInfo

# ==============================================================================
# CONFIGURACIÓN
# ==============================================================================

CANALES = [
    {
        "id": "FOX MX",
        "nombre": "FOX MX",
        "url_slug": "fox_mexico",
        "logo": "https://imagenes.gatotv.com/logos/canales/oscuros/fox-mediano.png",
    },
    {
        "id": "FOX+ MX",
        "nombre": "FOX+ MX",
        "url_slug": "fox_plus_centroamerica",
        "logo": "https://imagenes.gatotv.com/logos/canales/oscuros/fox_plus-mediano.png",
    },
    {
        "id": "Canal 5 MX",
        "nombre": "Canal 5 MX",
        "url_slug": "5_mexico",
        "logo": "https://imagenes.gatotv.com/logos/canales/oscuros/5_de_mexico-mediano.png",
    },
]

DIAS = 3
ZONA_MX = ZoneInfo("America/Mexico_City")
ZONA_ES = ZoneInfo("Europe/Madrid")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "es-MX,es;q=0.9",
}

HORA_RE = re.compile(r"^\d{1,2}:\d{2}\s*(AM|PM)$", re.IGNORECASE)

# ==============================================================================
# FUNCIONES
# ==============================================================================

def convertir_hora(hora_str, fecha_mx_base):
    """ Convierte '12:30 AM' en fecha_mx_base a datetime ES y MX """
    try:
        t = datetime.strptime(hora_str.strip(), "%I:%M %p")
    except ValueError:
        return None, None

    dt_mx = fecha_mx_base.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
    # Hacemos aware
    dt_mx = dt_mx.replace(tzinfo=ZONA_MX)
    dt_es = dt_mx.astimezone(ZONA_ES)
    return dt_mx, dt_es

def extraer_titulo_y_desc(celda):
    enlace = celda.find("a")
    titulo = enlace.get_text(strip=True) if enlace else ""
    if not titulo:
        texto = celda.get_text(separator="\n", strip=True)
        titulo = [l.strip() for l in texto.split("\n") if l.strip()][0] if texto else ""
    
    desc = ""
    for tag in celda.find_all(["p", "span", "small"]):
        t = tag.get_text(strip=True)
        if t and t != titulo:
            desc = t
            break
    return titulo, desc

def raspar_canal_dia(slug, fecha_mx):
    fecha_str = fecha_mx.strftime("%Y-%m-%d")
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
    vistos = set()

    for tabla in soup.find_all("table"):
        for fila in tabla.find_all("tr"):
            celdas = fila.find_all("td")
            textos = [c.get_text(strip=True) for c in celdas if c.get_text(strip=True)]
            if len(textos) < 3:
                continue

            h_ini_txt, h_fin_txt = textos[0], textos[1]
            if not HORA_RE.match(h_ini_txt) or not HORA_RE.match(h_fin_txt):
                continue

            celdas_con_texto = [c for c in celdas if c.get_text(strip=True)]
            if len(celdas_con_texto) < 3:
                continue

            titulo, desc = extraer_titulo_y_desc(celdas_con_texto[2])
            if not titulo:
                continue

            dt_mx_ini, dt_es_ini = convertir_hora(h_ini_txt, fecha_mx)
            dt_mx_fin, dt_es_fin = convertir_hora(h_fin_txt, fecha_mx)

            if not dt_mx_ini or not dt_mx_fin:
                continue

            # FIX del bug 00:00-00:30: si fin <= inicio, es día siguiente en MX
            if dt_mx_fin <= dt_mx_ini:
                dt_mx_fin += timedelta(days=1)
                dt_es_fin += timedelta(days=1)

            inicio_xml = dt_es_ini.strftime("%Y%m%d%H%M%S %z")
            fin_xml = dt_es_fin.strftime("%Y%m%d%H%M%S %z")

            clave = f"{inicio_xml}|{titulo}"
            if clave in vistos:
                continue
            vistos.add(clave)

            programas.append({
                "titulo": titulo,
                "desc": desc,
                "inicio": inicio_xml,
                "fin": fin_xml,
                "dt_es_ini": dt_es_ini # para ordenar
            })

    programas.sort(key=lambda x: x["dt_es_ini"])
    print(f"  ✓ {len(programas)} programas para {fecha_str}")
    return programas

def generar_xml(canales_data):
    tv = ET.Element("tv")
    tv.set("generator-info-name", "scraper_epg.py v2")
    tv.set("generator-info-url", "https://github.com")

    for canal in canales_data:
        ch = ET.SubElement(tv, "channel")
        ch.set("id", canal["id"])
        dn = ET.SubElement(ch, "display-name")
        dn.text = canal["nombre"]
        if canal.get("logo"):
            icon = ET.SubElement(ch, "icon")
            icon.set("src", canal["logo"])

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

def main():
    print("═══ INICIANDO SCRAPER EPG GATOTV V2 ═══")
    print(f"  Zona MX: {ZONA_MX} | Zona ES: {ZONA_ES}")

    hoy_mx = datetime.now(ZONA_MX).replace(hour=0, minute=0, second=0, microsecond=0)
    fechas = [hoy_mx + timedelta(days=i) for i in range(DIAS)]

    canales_data = []
    for canal in CANALES:
        print(f"\n─── Canal: {canal['nombre']} ───")
        todos = []
        for fecha in fechas:
            todos.extend(raspar_canal_dia(canal["url_slug"], fecha))
            time.sleep(1.5)
        # Limpia el campo auxiliar
        for p in todos: p.pop("dt_es_ini", None)
        canales_data.append({**canal, "programas": todos})
        print(f"  ═► Total: {len(todos)} programas en {DIAS} días")

    xml_output = generar_xml(canales_data)
    with open("guide.xml", "w", encoding="UTF-8") as f:
        f.write(xml_output)
    print(f"\n✓ guide.xml generado")

if __name__ == "__main__":
    main()
