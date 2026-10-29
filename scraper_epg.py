#!/usr/bin/env python3
# scraper_epg.py FIX horas - Basado en tu archivo que sí funciona
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
from xml.dom import minidom
import time
import re
from zoneinfo import ZoneInfo

ZONA_MX = ZoneInfo("America/Mexico_City")
ZONA_ES = ZoneInfo("Europe/Madrid")

CANALES = [
    {"id": "FOX MX", "nombre": "FOX MX", "url_slug": "fox_mexico", "logo": "https://imagenes.gatotv.com/logos/canales/oscuros/fox-mediano.png"},
    {"id": "FOX+ MX", "nombre": "FOX+ MX", "url_slug": "fox_plus_centroamerica", "logo": "https://imagenes.gatotv.com/logos/canales/oscuros/fox_plus-mediano.png"},
    {"id": "Canal 5 MX", "nombre": "Canal 5 MX", "url_slug": "5_mexico", "logo": "https://imagenes.gatotv.com/logos/canales/oscuros/5_de_mexico-mediano.png"},
]
DIAS = 3
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "es-MX,es;q=0.9",
}
# Ahora acepta AM/PM y 24h "00:00" y "00:00 - 00:30"
HORA_AMPM_RE = re.compile(r"^\d{1,2}:\d{2}\s*(AM|PM)$", re.IGNORECASE)
HORA_24_RE = re.compile(r"^\d{1,2}:\d{2}$")
HORA_RANGO_24_RE = re.compile(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})")

def convertir_hora(hora_str, fecha_base_mx):
    """Toma hora de GatoTV como hora MX y la convierte a ES +0100"""
    hora_str = hora_str.strip()
    try:
        # Prueba AM/PM
        if "M" in hora_str.upper():
            t = datetime.strptime(hora_str, "%I:%M %p")
        else:
            t = datetime.strptime(hora_str, "%H:%M")
    except:
        return None

    dt_mx = fecha_base_mx.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0, tzinfo=ZONA_MX)
    dt_es = dt_mx.astimezone(ZONA_ES)
    return dt_es

def extraer_titulo_y_desc(celda):
    enlace = celda.find("a")
    if enlace:
        titulo = enlace.get_text(strip=True)
    else:
        texto_completo = celda.get_text(separator="\n", strip=True)
        lineas = [l.strip() for l in texto_completo.split("\n") if l.strip()]
        titulo = lineas[0] if lineas else ""
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
            textos = [c.get_text(separator=" ", strip=True) for c in celdas]
            textos = [t for t in textos if t]
            if len(textos) < 2:
                continue

            # Soporta 3 formatos:
            # 1) "00:00 - 00:30" en una celda (tu foto)
            # 2) "00:00" | "00:30" en dos celdas
            # 3) "12:00 AM" | "12:30 AM"
            h_ini_txt = h_fin_txt = None
            idx_prog = 1

            # Formato 1: rango en primera celda
            m = HORA_RANGO_24_RE.search(textos[0])
            if m:
                h_ini_txt, h_fin_txt = m.group(1), m.group(2)
                idx_prog = 1
            elif len(textos) >= 2:
                # Formato 2 y 3
                if (HORA_24_RE.match(textos[0]) and HORA_24_RE.match(textos[1])) or \
                   (HORA_AMPM_RE.match(textos[0]) and HORA_AMPM_RE.match(textos[1])):
                    h_ini_txt, h_fin_txt = textos[0], textos[1]
                    idx_prog = 2

            if not h_ini_txt or not h_fin_txt:
                continue

            celdas_con_texto = [c for c in celdas if c.get_text(strip=True)]
            if len(celdas_con_texto) <= idx_prog:
                continue
            celda_prog = celdas_con_texto[idx_prog]
            titulo, desc = extraer_titulo_y_desc(celda_prog)
            if not titulo or len(titulo) < 3:
                continue
            if titulo.lower() in ["hora", "programa", "madrugada", "mañana", "tarde", "noche"]:
                continue

            dt_es_ini = convertir_hora(h_ini_txt, fecha_mx)
            dt_es_fin = convertir_hora(h_fin_txt, fecha_mx)
            if not dt_es_ini or not dt_es_fin:
                continue
            if dt_es_fin <= dt_es_ini:
                dt_es_fin += timedelta(days=1)

            inicio_str = dt_es_ini.strftime("%Y%m%d%H%M%S %z")
            fin_str = dt_es_fin.strftime("%Y%m%d%H%M%S %z")

            clave = f"{inicio_str}|{titulo}"
            if clave in vistos:
                continue
            vistos.add(clave)

            programas.append({
                "titulo": titulo,
                "desc": desc,
                "inicio": inicio_str,
                "fin": fin_str,
                "ini_dt": dt_es_ini
            })

    programas.sort(key=lambda x: x["ini_dt"])
    for p in programas: p.pop("ini_dt", None)
    print(f"  ✓ {len(programas)} programas para {fecha_str}")
    return programas

def generar_xml(canales_data):
    tv = ET.Element("tv")
    tv.set("generator-info-name", "scraper_epg.py")
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
    print("═══ INICIANDO SCRAPER EPG GATOTV FIX HORAS ═══")
    # Siempre base en MX para convertir a ES, así GitHub no da +0000
    hoy_mx = datetime.now(ZONA_MX).replace(hour=0, minute=0, second=0, microsecond=0)
    fechas = [hoy_mx + timedelta(days=i) for i in range(DIAS)]
    print(f"  Base MX: {hoy_mx} -> Salida ES: {ZONA_ES}")

    canales_data = []
    for canal in CANALES:
        print(f"\n─── Canal: {canal['nombre']} ───")
        todos = []
        for fecha in fechas:
            todos.extend(raspar_canal_dia(canal["url_slug"], fecha))
            time.sleep(1.5)
        canales_data.append({**canal, "programas": todos})
        print(f"  ═► Total: {len(todos)} programas")

    xml_output = generar_xml(canales_data)
    open("guide.xml", "w", encoding="UTF-8").write(xml_output)
    print(f"\n✓ guide.xml generado en +0100 - nunca +0000")

if __name__ == "__main__":
    main()
