#!/usr/bin/env python3
# Script: scraper_epg.py - VERSIÓN CORREGIDA
# Problema original: GatoTV te geolocaliza. Si lo abres desde España te muestra
# la hora ya en +0100, pero tu script asumía que siempre venía en -0600 y le sumaba +7h.
# Resultado: horarios desplazados 7 horas y programas que no coinciden.

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET
from xml.dom import minidom
import time, re

# Zonas reales
TZ_MEXICO = ZoneInfo("America/Mexico_City")       # -06:00
TZ_CENTRO = ZoneInfo("America/Costa_Rica")        # -06:00 (sin horario verano)
TZ_ESPANA = ZoneInfo("Europe/Madrid")             # +01:00 invierno / +02:00 verano

CANALES = [
    {
        "id": "FOX MX",
        "nombre": "FOX MX",
        "url_slug": "fox_mexico",
        "tz_origen": TZ_MEXICO,
        "logo": "https://imagenes.gatotv.com/logos/canales/oscuros/fox-mediano.png",
    },
    {
        "id": "FOX+ MX",
        "nombre": "FOX+ MX",
        "url_slug": "fox_plus_centroamerica",
        "tz_origen": TZ_CENTRO,  # ¡Este es Centroamérica, no México!
        "logo": "https://imagenes.gatotv.com/logos/canales/oscuros/fox_plus-mediano.png",
    },
    {
        "id": "Canal 5 MX",
        "nombre": "Canal 5 MX",
        "url_slug": "5_mexico",
        "tz_origen": TZ_MEXICO,
        "logo": "https://imagenes.gatotv.com/logos/canales/oscuros/5_de_mexico-mediano.png",
    },
]

DIAS = 3
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "es-CR,es;q=0.9",  # Fuerza que no te geolocalice a España
}
HORA_RE = re.compile(r"^\d{1,2}:\d{2}\s*(AM|PM)$", re.I)

def parse_hora_mexico(hora_str, fecha_local, tz_origen):
    """hora_str como '3:30 PM' + fecha_local (date) en tz_origen -> datetime aware"""
    t = datetime.strptime(hora_str.strip(), "%I:%M %p")
    dt = datetime(fecha_local.year, fecha_local.month, fecha_local.day,
                  t.hour, t.minute, tzinfo=tz_origen)
    return dt

def raspar_canal_dia(slug, tz_origen, fecha_origen):
    fecha_str = fecha_origen.strftime("%Y-%m-%d")
    url = f"https://www.gatotv.com/canal/{slug}/{fecha_str}"
    print(f"  → {url} (origen {tz_origen})")
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"  ✗ {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    programas = []
    vistos = set()

    for tabla in soup.find_all("table"):
        for fila in tabla.find_all("tr"):
            celdas = [c for c in fila.find_all("td") if c.get_text(strip=True)]
            if len(celdas) < 3:
                continue
            hi = celdas[0].get_text(strip=True)
            hf = celdas[1].get_text(strip=True)
            if not HORA_RE.match(hi) or not HORA_RE.match(hf):
                continue
            
            # titulo
            celda_prog = celdas[2]
            titulo = celda_prog.find("a").get_text(strip=True) if celda_prog.find("a") else celda_prog.get_text(separator=" ", strip=True).split("\n")[0]
            if not titulo:
                continue

            # Si cruza medianoche en origen
            fin_fecha = fecha_origen
            if "PM" in hi.upper() and "AM" in hf.upper():
                fin_fecha = fecha_origen + timedelta(days=1)

            dt_ini_origen = parse_hora_mexico(hi, fecha_origen, tz_origen)
            dt_fin_origen = parse_hora_mexico(hf, fin_fecha, tz_origen)

            # Convertir a España
            dt_ini_esp = dt_ini_origen.astimezone(TZ_ESPANA)
            dt_fin_esp = dt_fin_origen.astimezone(TZ_ESPANA)

            # XMLTV requiere +0100 / +0200
            inicio_str = dt_ini_esp.strftime("%Y%m%d%H%M%S %z")
            fin_str = dt_fin_esp.strftime("%Y%m%d%H%M%S %z")

            clave = f"{inicio_str}|{titulo}"
            if clave in vistos:
                continue
            vistos.add(clave)

            programas.append({"titulo": titulo, "inicio": inicio_str, "fin": fin_str, "dt_sort": dt_ini_esp})

    # Ordenar por hora real
    programas.sort(key=lambda x: x["dt_sort"])
    for p in programas:
        p.pop("dt_sort", None)
    print(f"  ✓ {len(programas)} programas")
    return programas

def generar_xml(canales_data):
    tv = ET.Element("tv", {"generator-info-name": "scraper_epg_fixed"})
    for canal in canales_data:
        ch = ET.SubElement(tv, "channel", id=canal["id"])
        ET.SubElement(ch, "display-name").text = canal["nombre"]
        if canal["logo"]:
            ET.SubElement(ch, "icon", src=canal["logo"])
    for canal in canales_data:
        for prog in canal["programas"]:
            pr = ET.SubElement(tv, "programme", start=prog["inicio"], stop=prog["fin"], channel=canal["id"])
            ET.SubElement(pr, "title", lang="es").text = prog["titulo"]
    xml_str = ET.tostring(tv, encoding="unicode")
    return minidom.parseString(xml_str).toprettyxml(indent="  ", encoding="UTF-8").decode()

def main():
    print("=== SCRAPER CORREGIDO ===")
    # Usamos fecha de origen (México/Centroamérica) no UTC
    hoy_centro = datetime.now(TZ_CENTRO).replace(hour=0, minute=0, second=0, microsecond=0)
    fechas = {
        c["id"]: [hoy_centro.astimezone(c["tz_origen"]).replace(tzinfo=None) for _ in range(DIAS)]
        for c in CANALES
    }
    # Simplificado: 3 días desde hoy en cada zona origen
    canales_data = []
    for canal in CANALES:
        print(f"\n--- {canal['nombre']} ---")
        todos = []
        base = datetime.now(canal["tz_origen"]).replace(hour=0, minute=0, second=0, microsecond=0)
        for i in range(DIAS):
            f = (base + timedelta(days=i)).replace(tzinfo=None)
            # pasamos date sin tzinfo pero parse_hora lo pone
            todos.extend(raspar_canal_dia(canal["url_slug"], canal["tz_origen"], datetime(f.year, f.month, f.day)))
            time.sleep(1)
        canales_data.append({**canal, "programas": todos})

    xml = generar_xml(canales_data)
    open("guide_fixed.xml","w",encoding="utf-8").write(xml)
    print("\n✓ guide_fixed.xml generado")

if __name__ == "__main__":
    main()
