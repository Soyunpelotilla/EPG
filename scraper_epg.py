#!/usr/bin/env python3
# scraper_epg.py v3.1 FINAL
# FIX: Captura 00:00-00:30 en una sola celda como en tu foto + nunca +0000
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
from xml.dom import minidom
import time
import re
from zoneinfo import ZoneInfo

CANALES = [
    {"id": "FOX MX", "nombre": "FOX MX", "url_slug": "fox_mexico", "logo": "https://imagenes.gatotv.com/logos/canales/oscuros/fox-mediano.png"},
    {"id": "FOX+ MX", "nombre": "FOX+ MX", "url_slug": "fox_plus_centroamerica", "logo": "https://imagenes.gatotv.com/logos/canales/oscuros/fox_plus-mediano.png"},
    {"id": "Canal 5 MX", "nombre": "Canal 5 MX", "url_slug": "5_mexico", "logo": "https://imagenes.gatotv.com/logos/canales/oscuros/5_de_mexico-mediano.png"},
]

DIAS = 3
ZONA_ES = ZoneInfo("Europe/Madrid")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "es-ES,es;q=0.9",
}
HORA_RE = re.compile(r"^\d{1,2}:\d{2}$")
HORA_RANGO_RE = re.compile(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})")

def extraer_titulo_y_desc(celda):
    enlace = celda.find("a")
    titulo = enlace.get_text(strip=True) if enlace else celda.get_text(strip=True)
    titulo = titulo.split("\n")[0].strip()
    return titulo, ""

def parse_hora_es(hora_str, fecha_base_es):
    t = datetime.strptime(hora_str.strip(), "%H:%M")
    dt = fecha_base_es.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0, tzinfo=ZONA_ES)
    return dt

def raspar_canal_dia(slug, fecha_es):
    url = f"https://www.gatotv.com/canal/{slug}/{fecha_es.strftime('%Y-%m-%d')}"
    print(f"  → {url}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"  ✗ {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    programas = []

    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 2: continue
        
        # Tu foto: primera td = "00:00 - 00:30"
        primera = tds[0].get_text(" ", strip=True)
        m = HORA_RANGO_RE.search(primera)
        if not m:
            continue
        
        h_ini_txt, h_fin_txt = m.group(1), m.group(2)
        celda_prog = tds[1] if len(tds) >= 2 else None
        if not celda_prog: continue

        titulo, desc = extraer_titulo_y_desc(celda_prog)
        if not titulo or titulo.lower() in ["hora", "programa", "madrugada", "mañana", "tarde", "noche"]: 
            continue
        if len(titulo) < 3: continue

        dt_ini = parse_hora_es(h_ini_txt, fecha_es)
        dt_fin = parse_hora_es(h_fin_txt, fecha_es)
        if dt_fin <= dt_ini:
            dt_fin += timedelta(days=1)

        programas.append({
            "titulo": titulo,
            "desc": desc,
            "ini_dt": dt_ini,
            "inicio": dt_ini.strftime("%Y%m%d%H%M%S %z"),
            "fin": dt_fin.strftime("%Y%m%d%H%M%S %z"),
        })

    programas.sort(key=lambda x: x["ini_dt"])
    # Solo duplicados exactos, no borres el directo
    filtrados = []
    vistos = set()
    for p in programas:
        k = f"{p['inicio']}-{p['titulo']}"
        if k not in vistos:
            vistos.add(k)
            filtrados.append(p)
    
    for p in filtrados: p.pop("ini_dt", None)
    print(f"  ✓ {len(filtrados)} programas")
    return filtrados

def generar_xml(canales_data):
    tv = ET.Element("tv")
    tv.set("generator-info-name", "scraper_epg.py v3.1")
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
    print("═══ SCRAPER V3.1 - DIRECTO ESPAÑA PRIMERO ═══")
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
    open("guide.xml", "w", encoding="UTF-8").write(generar_xml(canales_data))
    print("\n✓ guide.xml generado en +0100 - directo primero")

if __name__ == "__main__":
    main()
