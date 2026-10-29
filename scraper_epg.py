#!/usr/bin/env python3
# scraper_epg.py v3 FINAL
# - Siempre escribe en hora España +0100/+0200, nunca +0000
# - Funciona igual en tu PC y en 【entity-GitHub¦canonical_name=GitHub】 Actions
# - GatoTV ya viene en ES desde España, lo tomamos tal cual

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
HORA_RE = re.compile(r"^\d{1,2}:\d{2}\s*(AM|PM)$", re.IGNORECASE)

def extraer_titulo_y_desc(celda):
    enlace = celda.find("a")
    titulo = enlace.get_text(strip=True) if enlace else ""
    if not titulo:
        txt = celda.get_text(separator="\n", strip=True)
        titulo = [l for l in txt.split("\n") if l.strip()][0] if txt else ""
    desc = ""
    for tag in celda.find_all(["p","span","small"]):
        t = tag.get_text(strip=True)
        if t and t != titulo:
            desc = t
            break
    return titulo, desc

def parse_hora_es(hora_str, fecha_base_es):
    """Toma '12:00 AM' como hora de España directamente"""
    try:
        t = datetime.strptime(hora_str.strip(), "%I:%M %p")
    except:
        return None
    dt = fecha_base_es.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
    # Forzamos +0100 / +0200 SIEMPRE
    dt = dt.replace(tzinfo=ZONA_ES)
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

    for tabla in soup.find_all("table"):
        for fila in tabla.find_all("tr"):
            celdas = [c for c in fila.find_all("td") if c.get_text(strip=True)]
            if len(celdas) < 3: continue
            textos = [c.get_text(strip=True) for c in celdas]
            if not HORA_RE.match(textos[0]) or not HORA_RE.match(textos[1]): continue
            
            titulo, desc = extraer_titulo_y_desc(celdas[2])
            if not titulo: continue

            dt_ini = parse_hora_es(textos[0], fecha_es)
            dt_fin = parse_hora_es(textos[1], fecha_es)
            if not dt_ini or not dt_fin: continue

            # 00:00 - 00:30 -> fin <= inicio = día siguiente
            if dt_fin <= dt_ini:
                dt_fin += timedelta(days=1)

            programas.append({"titulo": titulo, "desc": desc, "ini": dt_ini, "fin": dt_fin})

    programas.sort(key=lambda x: x["ini"])
    # Filtro anti-solape
    filtrados = []
    for p in programas:
        if not filtrados or p["ini"] >= filtrados[-1]["fin"]:
            filtrados.append(p)
    
    resultado = []
    for p in filtrados:
        resultado.append({
            "titulo": p["titulo"],
            "desc": p["desc"],
            "inicio": p["ini"].strftime("%Y%m%d%H%M%S %z"),
            "fin": p["fin"].strftime("%Y%m%d%H%M%S %z"),
        })
    print(f"  ✓ {len(resultado)} programas")
    return resultado

def generar_xml(canales_data):
    tv = ET.Element("tv")
    tv.set("generator-info-name", "scraper_epg.py v3")
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
            if prog.get("desc"):
                d = ET.SubElement(pr, "desc")
                d.set("lang", "es")
                d.text = prog["desc"]
    xml_str = ET.tostring(tv, encoding="unicode")
    return minidom.parseString(xml_str).toprettyxml(indent="  ", encoding="UTF-8").decode("UTF-8")

def main():
    print("═══ SCRAPER V3 - SIEMPRE +0100 ═══")
    # BASE SIEMPRE EN ESPAÑA, aunque 【entity-GitHub¦canonical_name=GitHub】 esté en UTC
    hoy_es = datetime.now(ZONA_ES).replace(hour=0, minute=0, second=0, microsecond=0)
    fechas = [hoy_es + timedelta(days=i) for i in range(DIAS)]

    canales_data = []
    for canal in CANALES:
        print(f"\n─── {canal['nombre']} ───")
        todos = []
        for f in fechas:
            todos.extend(raspar_canal_dia(canal["url_slug"], f))
            time.sleep(1.2)
        canales_data.append({**canal, "programas": todos})

    open("guide.xml", "w", encoding="UTF-8").write(generar_xml(canales_data))
    print("\n✓ guide.xml generado en +0100")

if __name__ == "__main__":
    main()
