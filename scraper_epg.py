#!/usr/bin/env python3
# scraper_epg_fixed_v2.py - con rango -1 para no perder madrugada

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET
from xml.dom import minidom
import time
import re

TZ_MADRID = ZoneInfo("Europe/Madrid")
TZ_MEXICO_OFFSET = 6

CANALES = [
    {"id": "FOX MX","nombre": "FOX MX","url_slug": "fox_mexico","logo": "https://imagenes.gatotv.com/logos/canales/oscuros/fox-mediano.png",},
    {"id": "FOX+ MX","nombre": "FOX+ MX","url_slug": "fox_plus_centroamerica","logo": "https://imagenes.gatotv.com/logos/canales/oscuros/fox_plus-mediano.png",},
    {"id": "Canal 5 MX","nombre": "Canal 5 MX","url_slug": "5_mexico","logo": "https://imagenes.gatotv.com/logos/canales/oscuros/5_de_mexico-mediano.png",},
]

DIAS = 3
DIAS_ATRAS = 1  # nuevo: pide ayer tambien

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "es-MX,es;q=0.9",
}

HORA_RE = re.compile(r"^\d{1,2}:\d{2}\s*(AM|PM)$", re.IGNORECASE)

def get_timezone_espana():
    ahora = datetime.now(TZ_MADRID)
    print(f"  Zona España: {ahora.strftime('%z')} ({ahora.tzname()}) - {ahora}")
    return ahora.strftime("%z")

def convertir_hora_a_espana(hora_str, fecha_base):
    try:
        t = datetime.strptime(hora_str.strip(), "%I:%M %p")
    except:
        return None
    fecha_mx_naive = datetime(fecha_base.year, fecha_base.month, fecha_base.day, t.hour, t.minute)
    dt_utc_real = fecha_mx_naive + timedelta(hours=TZ_MEXICO_OFFSET)
    dt_utc_real = dt_utc_real.replace(tzinfo=ZoneInfo("UTC"))
    dt_espana = dt_utc_real.astimezone(TZ_MADRID)
    return dt_espana.strftime("%Y%m%d%H%M%S %z")

def extraer_titulo_y_desc(celda):
    enlace = celda.find("a")
    titulo = enlace.get_text(strip=True) if enlace else celda.get_text(separator="\n", strip=True).split("\n")[0].strip()
    desc = ""
    for tag in celda.find_all(["p","span","small"]):
        tt = tag.get_text(strip=True)
        if tt and tt != titulo:
            desc = tt
            break
    return titulo, desc

def raspar_canal_dia(slug, fecha, session):
    fecha_str = fecha.strftime("%Y-%m-%d")
    url = f"https://www.gatotv.com/canal/{slug}/{fecha_str}"
    print(f"  → {url}")
    try:
        resp = session.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"  ✗ {e}")
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    programas = []
    for tabla in soup.find_all("table"):
        for fila in tabla.find_all("tr"):
            celdas = fila.find_all("td")
            textos = [c.get_text(strip=True) for c in celdas if c.get_text(strip=True)]
            if len(textos) < 3: continue
            if not HORA_RE.match(textos[0]) or not HORA_RE.match(textos[1]): continue
            celdas_con_texto = [c for c in celdas if c.get_text(strip=True)]
            if len(celdas_con_texto) < 3: continue
            titulo, desc = extraer_titulo_y_desc(celdas_con_texto[2])
            if not titulo: continue
            fin_fecha = fecha + timedelta(days=1) if ("PM" in textos[0].upper() and "AM" in textos[1].upper()) else fecha
            inicio_dt = convertir_hora_a_espana(textos[0], fecha)
            fin_dt = convertir_hora_a_espana(textos[1], fin_fecha)
            if not inicio_dt or not fin_dt: continue
            programas.append({"titulo": titulo, "desc": desc, "inicio": inicio_dt, "fin": fin_dt})
    programas.sort(key=lambda x: x["inicio"])
    print(f"  ✓ {len(programas)} para {fecha_str}")
    return programas

def generar_xml(canales_data):
    tv = ET.Element("tv")
    tv.set("generator-info-name", "scraper_epg_fixed_v2.py")
    for canal in canales_data:
        ch = ET.SubElement(tv, "channel")
        ch.set("id", canal["id"])
        ET.SubElement(ch, "display-name").text = canal["nombre"]
        if canal.get("logo"):
            ET.SubElement(ch, "icon").set("src", canal["logo"])
    for canal in canales_data:
        # deduplicar por inicio+titulo para el rango solapado
        vistos = set()
        for prog in sorted(canal["programas"], key=lambda x: x["inicio"]):
            clave = f"{prog['inicio']}|{prog['titulo']}"
            if clave in vistos: continue
            vistos.add(clave)
            pr = ET.SubElement(tv, "programme")
            pr.set("start", prog["inicio"])
            pr.set("stop", prog["fin"])
            pr.set("channel", canal["id"])
            ET.SubElement(pr, "title", lang="es").text = prog["titulo"]
            if prog.get("desc"):
                ET.SubElement(pr, "desc", lang="es").text = prog["desc"]
    xml_str = ET.tostring(tv, encoding="unicode")
    dom = minidom.parseString(xml_str)
    pretty = dom.toprettyxml(indent="  ", encoding="UTF-8").decode("UTF-8")
    return "\n".join([l for l in pretty.split("\n") if l.strip()])

def main():
    print("═══ SCRAPER FIXED V2 (con ayer) ═══")
    tz = get_timezone_espana()
    hoy_madrid = datetime.now(TZ_MADRID).replace(hour=0, minute=0, second=0, microsecond=0)
    fechas = [hoy_madrid + timedelta(days=i) for i in range(-DIAS_ATRAS, DIAS)]
    print(f"Fechas: {[f.strftime('%Y-%m-%d') for f in fechas]}")

    canales_data = []
    session = requests.Session()
    for canal in CANALES:
        print(f"\n─── {canal['nombre']} ───")
        todos = []
        for fecha in fechas:
            todos.extend(raspar_canal_dia(canal["url_slug"], fecha, session))
            time.sleep(1.2)
        canales_data.append({**canal, "programas": todos})
        print(f"  ═► Total {len(todos)}")

    xml_out = generar_xml(canales_data)
    with open("guide.xml", "w", encoding="UTF-8") as f:
        f.write(xml_out)
    print(f"\n✓ guide.xml generado")

if __name__ == "__main__":
    main()
