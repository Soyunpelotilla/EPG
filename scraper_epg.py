#!/usr/bin/env python3
# scraper_epg.py v3.2 FIX - No más guide.xml vacío
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
from xml.dom import minidom
import time
import re
from zoneinfo import ZoneInfo
import sys

CANALES = [
    {"id": "FOX MX", "nombre": "FOX MX", "url_slug": "fox_mexico", "logo": "https://imagenes.gatotv.com/logos/canales/oscuros/fox-mediano.png"},
    {"id": "FOX+ MX", "nombre": "FOX+ MX", "url_slug": "fox_plus_centroamerica", "logo": "https://imagenes.gatotv.com/logos/canales/oscuros/fox_plus-mediano.png"},
    {"id": "Canal 5 MX", "nombre": "Canal 5 MX", "url_slug": "5_mexico", "logo": "https://imagenes.gatotv.com/logos/canales/oscuros/5_de_mexico-mediano.png"},
]

DIAS = 3
ZONA_ES = ZoneInfo("Europe/Madrid")
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Language": "es-ES,es;q=0.9"}
HORA_RE = re.compile(r"^\d{1,2}:\d{2}$")
HORA_RANGO_RE = re.compile(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})")

def parse_hora_es(hora_str, fecha_base_es):
    try:
        t = datetime.strptime(hora_str.strip(), "%H:%M")
        return fecha_base_es.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0, tzinfo=ZONA_ES)
    except Exception as e:
        print(f"    ! Hora no válida '{hora_str}': {e}")
        return None

def raspar_canal_dia(slug, fecha_es):
    url = f"https://www.gatotv.com/canal/{slug}/{fecha_es.strftime('%Y-%m-%d')}"
    print(f"  → {url}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
    except Exception as e:
        print(f"  ✗ Error HTTP: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    programas = []

    for tr in soup.find_all("tr"):
        try:
            tds = tr.find_all("td")
            if len(tds) < 2:
                continue

            h_ini_txt = h_fin_txt = None
            idx_prog = 1

            # Caso 1: tu foto -> "00:00 - 00:30" en td[0]
            m = HORA_RANGO_RE.search(tds[0].get_text(" ", strip=True))
            if m:
                h_ini_txt, h_fin_txt = m.group(1), m.group(2)
                idx_prog = 1
            # Caso 2: formato antiguo -> td[0]=00:00 td[1]=00:30
            elif len(tds) >= 2 and HORA_RE.match(tds[0].get_text(strip=True)) and HORA_RE.match(tds[1].get_text(strip=True)):
                h_ini_txt = tds[0].get_text(strip=True)
                h_fin_txt = tds[1].get_text(strip=True)
                idx_prog = 2

            if not h_ini_txt or not h_fin_txt:
                continue

            celda_prog = tds[idx_prog] if len(tds) > idx_prog else None
            if not celda_prog:
                continue

            titulo = celda_prog.get_text(" ", strip=True).split("\n")[0].strip()
            if not titulo or len(titulo) < 3 or titulo.lower() in ["hora", "programa", "madrugada", "mañana", "tarde", "noche", "horarios de programación"]:
                continue

            dt_ini = parse_hora_es(h_ini_txt, fecha_es)
            dt_fin = parse_hora_es(h_fin_txt, fecha_es)
            if not dt_ini or not dt_fin:
                continue
            if dt_fin <= dt_ini:
                dt_fin += timedelta(days=1)

            programas.append({
                "titulo": titulo,
                "inicio": dt_ini.strftime("%Y%m%d%H%M%S %z"),
                "fin": dt_fin.strftime("%Y%m%d%H%M%S %z"),
                "ini_dt": dt_ini
            })
        except Exception as e:
            print(f"    ! Fila saltada: {e}")
            continue

    programas.sort(key=lambda x: x["ini_dt"])
    # Solo quita duplicados exactos
    filtrados = []
    vistos = set()
    for p in programas:
        k = f"{p['inicio']}-{p['titulo']}"
        if k not in vistos:
            vistos.add(k)
            filtrados.append({k: v for k, v in p.items() if k != "ini_dt"})
    
    print(f"  ✓ {len(filtrados)} programas (raw {len(programas)})")
    return filtrados

def generar_xml(canales_data):
    tv = ET.Element("tv")
    tv.set("generator-info-name", "scraper_epg.py v3.2")
    for canal in canales_data:
        ch = ET.SubElement(tv, "channel")
        ch.set("id", canal["id"])
        ET.SubElement(ch, "display-name").text = canal["nombre"]
        if canal.get("logo"):
            ET.SubElement(ch, "icon").set("src", canal["logo"])
    for canal in canales_data:
        for prog in canal["programas"]:
            pr = ET.SubElement(tv, "programme")
            pr.set("start", prog["inicio"])
            pr.set("stop", prog["fin"])
            pr.set("channel", canal["id"])
            t = ET.SubElement(pr, "title")
            t.set("lang", "es")
            t.text = prog["titulo"]
    xml_str = ET.tostring(tv, encoding="unicode")
    return minidom.parseString(xml_str).toprettyxml(indent="  ", encoding="UTF-8").decode("UTF-8")

def main():
    print("═══ SCRAPER V3.2 FIX - NUNCA VACIO ═══")
    hoy_es = datetime.now(ZONA_ES).replace(hour=0, minute=0, second=0, microsecond=0)
    fechas = [hoy_es + timedelta(days=i) for i in range(DIAS)]
    canales_data = []
    for canal in CANALES:
        print(f"\n─── {canal['nombre']} ───")
        todos = []
        for f in fechas:
            todos.extend(raspar_canal_dia(canal["url_slug"], f))
            time.sleep(1)
        canales_data.append({**canal, "programas": todos})

    total = sum(len(c["programas"]) for c in canales_data)
    if total == 0:
        print("\n✗ ERROR: 0 programas, no escribo guide.xml para no borrar el anterior")
        sys.exit(1)

    open("guide.xml", "w", encoding="UTF-8").write(generar_xml(canales_data))
    print(f"\n✓ guide.xml generado con {total} programas en +0100")

if __name__ == "__main__":
    main()
