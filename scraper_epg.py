#!/usr/bin/env python3
# scraper_epg.py FINAL - OFFSET 9 para Panthers 01:00 ES real
# Basado en FIXED V2 pero con offset corregido

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET
from xml.dom import minidom
import time
import re

TZ_MADRID = ZoneInfo("Europe/Madrid")
TZ_MEXICO_OFFSET = 7

print(f"═══ SCRAPER OFFSET {TZ_MEXICO_OFFSET}h (FIX PANTHERS 01:00) ═══")
print(f"  Zona España: {datetime.now(TZ_MADRID).tzname()} - {datetime.now(TZ_MADRID)}")

CANALES = [
    {"id": "FOX MX","nombre": "FOX MX","url_slug": "fox_mexico","logo": "https://imagenes.gatotv.com/logos/canales/oscuros/fox-mediano.png",},
    {"id": "FOX+ MX","nombre": "FOX+ MX","url_slug": "fox_plus_centroamerica","logo": "https://imagenes.gatotv.com/logos/canales/oscuros/fox_plus-mediano.png",},
    {"id": "Canal 5 MX","nombre": "Canal 5 MX","url_slug": "5_mexico","logo": "https://imagenes.gatotv.com/logos/canales/oscuros/5_de_mexico-mediano.png",},
]

DIAS = 3
DIAS_ATRAS = 1
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
HORA_RE = re.compile(r"^\d{1,2}:\d{2}\s*(AM|PM)$", re.IGNORECASE)

def convertir_hora(hora_str, fecha_base):
    try:
        t = datetime.strptime(hora_str.strip(), "%I:%M %p")
    except:
        return None, None
    fecha_mx = datetime(fecha_base.year, fecha_base.month, fecha_base.day, t.hour, t.minute)
    dt_utc = fecha_mx + timedelta(hours=TZ_MEXICO_OFFSET)
    dt_utc = dt_utc.replace(tzinfo=ZoneInfo("UTC"))
    dt_es = dt_utc.astimezone(TZ_MADRID)
    return dt_es, dt_es.strftime("%Y%m%d%H%M%S %z")

def raspar(slug, fecha, session):
    url = f"https://www.gatotv.com/canal/{slug}/{fecha.strftime('%Y-%m-%d')}"
    print(f"  → {url}")
    try:
        r = session.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"  ✗ {e}")
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    progs = []
    for tr in soup.find_all("tr"):
        tds = [c.get_text(strip=True) for c in tr.find_all("td") if c.get_text(strip=True)]
        if len(tds) < 3: continue
        if not HORA_RE.match(tds[0]) or not HORA_RE.match(tds[1]): continue
        celdas = [c for c in tr.find_all("td") if c.get_text(strip=True)]
        if len(celdas) < 3: continue
        titulo = celdas[2].find("a").get_text(strip=True) if celdas[2].find("a") else celdas[2].get_text(strip=True).split("\n")[0]
        fin_fecha = fecha + timedelta(days=1) if "PM" in tds[0].upper() and "AM" in tds[1].upper() else fecha
        dt_ini, str_ini = convertir_hora(tds[0], fecha)
        dt_fin, str_fin = convertir_hora(tds[1], fin_fecha)
        if dt_ini and dt_fin:
            progs.append({"titulo": titulo, "inicio": str_ini, "fin": str_fin, "dt_ini": dt_ini, "dt_fin": dt_fin})
    print(f"  ✓ {len(progs)} para {fecha.strftime('%Y-%m-%d')}")
    return progs

def main():
    hoy = datetime.now(TZ_MADRID).replace(hour=0, minute=0, second=0, microsecond=0)
    fechas = [hoy + timedelta(days=i) for i in range(-DIAS_ATRAS, DIAS)]
    print(f"Fechas: {[f.strftime('%Y-%m-%d') for f in fechas]}\n")
    session = requests.Session()
    canales_data = []
    for canal in CANALES:
        print(f"\n─── {canal['id']} ───")
        todos = []
        for f in fechas:
            todos.extend(raspar(canal["url_slug"], f, session))
            time.sleep(0.6)
        # deduplicar
        uniq = {}
        for p in sorted(todos, key=lambda x: x["dt_ini"]):
            uniq[f"{p['inicio']}|{p['titulo']}"] = p
        lista = list(uniq.values())
        print(f"  ═► Total {len(lista)}")
        canales_data.append({**canal, "programas": lista})

    tv = ET.Element("tv")
    tv.set("generator-info-name", f"scraper_epg.py OFFSET {TZ_MEXICO_OFFSET}h")
    tv.set("generator-info-url", "https://github.com/Soyunpelotilla/EPG")
    for c in canales_data:
        ch = ET.SubElement(tv, "channel")
        ch.set("id", c["id"])
        ET.SubElement(ch, "display-name").text = c["nombre"]
        if c.get("logo"):
            ET.SubElement(ch, "icon").set("src", c["logo"])
    for c in canales_data:
        for p in sorted(c["programas"], key=lambda x: x["inicio"]):
            pr = ET.SubElement(tv, "programme")
            pr.set("start", p["inicio"])
            pr.set("stop", p["fin"])
            pr.set("channel", c["id"])
            ET.SubElement(pr, "title", lang="es").text = p["titulo"]

    xml_str = ET.tostring(tv, encoding="unicode")
    pretty = minidom.parseString(xml_str).toprettyxml(indent="  ", encoding="UTF-8").decode("UTF-8")
    pretty = "\n".join([l for l in pretty.split("\n") if l.strip()])
    with open("guide.xml", "w", encoding="UTF-8") as f:
        f.write(pretty)
    print(f"\n✓ guide.xml generado con OFFSET {TZ_MEXICO_OFFSET}h - Panthers debe salir a las 01:00")

if __name__ == "__main__":
    main()
