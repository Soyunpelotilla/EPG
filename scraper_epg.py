#!/usr/bin/env python3
# scraper_epg.py FINAL FIX - Tu archivo que sí funciona + horas bien
# FIX: ZoneInfo en vez de ultimo_domingo() + soporte 24h "00:00 - 00:30"
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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "es-MX,es;q=0.9",
}
HORA_AMPM_RE = re.compile(r"^\d{1,2}:\d{2}\s*(AM|PM)$", re.IGNORECASE)
HORA_24_RE = re.compile(r"^\d{1,2}:\d{2}$")
HORA_RANGO_24_RE = re.compile(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})")

def convertir_hora_a_espana(hora_str, fecha_mx):
    """Convierte hora MX (texto de GatoTV) a ES usando ZoneInfo - siempre +0100/+0200 correcto"""
    hora_str = hora_str.strip()
    try:
        if "M" in hora_str.upper():
            t = datetime.strptime(hora_str, "%I:%M %p")
        else:
            t = datetime.strptime(hora_str, "%H:%M")
    except:
        return None
    # Fecha base en MX
    dt_mx = fecha_mx.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0, tzinfo=ZONA_MX)
    # Convierte a ES - ZoneInfo calcula solo si es +0100 o +0200
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

            h_ini_txt = h_fin_txt = None
            idx_prog = 1

            # Soporta "00:00 - 00:30" en una celda (tu foto)
            m = HORA_RANGO_24_RE.search(textos[0])
            if m:
                h_ini_txt, h_fin_txt = m.group(1), m.group(2)
                idx_prog = 1
            elif len(textos) >= 2:
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
            if titulo.lower() in ["hora", "programa", "madrugada", "mañana", "tarde", "noche", "horarios de programación"]:
                continue

            dt_es_ini = convertir_hora_a_espana(h_ini_txt, fecha_mx)
            dt_es_fin = convertir_hora_a_espana(h_fin_txt, fecha_mx)
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
    for p in programas:
        p.pop("ini_dt", None)
    print(f"  ✓ {len(programas)} programas para {fecha_str}")
    return programas

def generar_xml(canales_data):
    tv = ET.Element("tv")
    tv.set("generator-info-name", "scraper_epg.py")
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
    print("═══ INICIANDO SCRAPER EPG GATOTV FINAL FIX ═══")
    hoy_mx = datetime.now(ZONA_MX).replace(hour=0, minute=0, second=0, microsecond=0)
    fechas = [hoy_mx + timedelta(days=i) for i in range(DIAS)]
    print(f"  Base MX: {hoy_mx} -> Salida ES: {ZONA_ES} (ZoneInfo calcula +0100/+0200 solo)")

    canales_data = []
    for canal in CANALES:
        print(f"\n─── Canal: {canal['nombre']} ───")
        todos_programas = []
        for fecha in fechas:
            programas_dia = raspar_canal_dia(canal["url_slug"], fecha)
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
