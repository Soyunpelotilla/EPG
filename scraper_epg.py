#!/usr/bin/env python3
# ==============================================================================
# Script: scraper_epg_fixed.py
# Fix del original: usa Europe/Madrid real, corrige bug de medianoche UTC
# ==============================================================================

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET
from xml.dom import minidom
import time
import re

TZ_MADRID = ZoneInfo("Europe/Madrid")
TZ_MEXICO_OFFSET = 6  # Mexico Centro es UTC-6 (sin DST desde 2022)

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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "es-MX,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

HORA_RE = re.compile(r"^\d{1,2}:\d{2}\s*(AM|PM)$", re.IGNORECASE)

def get_timezone_espana():
    ahora = datetime.now(TZ_MADRID)
    offset = ahora.strftime("%z")
    # Formato XMLTV +0100
    offset_fmt = f"{offset[:3]}{offset[3:]}" if len(offset)==5 else ahora.strftime("%z")
    # Para XMLTV necesitamos +0100 / +0200
    tz_str = ahora.strftime("%z")
    # tz_str viene como +0100
    print(f"  Zona horaria España detectada: {tz_str} ({ahora.tzname()}) - {ahora}")
    return tz_str

def convertir_hora_a_espana(hora_str, fecha_madrid, tz_espana_str):
    """
    fecha_madrid: datetime a medianoche en Europe/Madrid del dia que raspamos
    hora_str: "05:30 PM" hora de Mexico
    """
    hora_str = hora_str.strip()
    try:
        t = datetime.strptime(hora_str, "%I:%M %p")
    except ValueError:
        return None

    # Creamos datetime de Mexico en fecha base
    # La web da la fecha en Mexico, pero nosotros raspamos por fecha Madrid
    # Para evitar el bug de medianoche, interpretamos la hora MX y luego convertimos
    dt_mexico_naive = fecha_madrid.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
    # Convertimos ese naive a UTC: Mexico = UTC-6
    # Si fecha_madrid es 2026-10-30 00:00 Madrid, son 2026-10-29 22:00 UTC en invierno
    # Por eso primero pasamos fecha_madrid a UTC, restamos offset MX y sumamos offset ES
    dt_madrid = dt_mexico_naive  # ya esta en hora Madrid, pero representa la hora MX
    # Forma correcta y simple: hora MX -> UTC -> Madrid
    dt_utc = dt_mexico_naive.replace(tzinfo=TZ_MADRID).astimezone(ZoneInfo("UTC")) + timedelta(hours=TZ_MEXICO_OFFSET)
    # Ahora dt_utc es la hora real UTC del programa
    # Pero necesitamos que si el programa es 17:30 MX del dia 29, sea 00:30 Madrid del 30
    # Entonces usamos la fecha base como fecha MX, no Madrid
    # Solucion: tratamos fecha_madrid como fecha MX para el calculo
    # Re-calculamos limpio:
    fecha_mx_naive = datetime(fecha_madrid.year, fecha_madrid.month, fecha_madrid.day, t.hour, t.minute)
    dt_utc_real = fecha_mx_naive + timedelta(hours=TZ_MEXICO_OFFSET)  # MX UTC-6 -> +6 = UTC
    dt_utc_real = dt_utc_real.replace(tzinfo=ZoneInfo("UTC"))
    dt_espana = dt_utc_real.astimezone(TZ_MADRID)

    return dt_espana.strftime("%Y%m%d%H%M%S %z")

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

def raspar_canal_dia(slug, fecha_madrid, tz_espana, session):
    fecha_str = fecha_madrid.strftime("%Y-%m-%d")
    url = f"https://www.gatotv.com/canal/{slug}/{fecha_str}"
    print(f"  → Raspando: {url}")

    try:
        resp = session.get(url, headers=HEADERS, timeout=20)
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
            if len(textos) < 3:
                continue

            hora_inicio_txt = textos[0]
            hora_fin_txt = textos[1]

            if not HORA_RE.match(hora_inicio_txt):
                continue
            if not HORA_RE.match(hora_fin_txt):
                continue

            celdas_con_texto = [c for c in celdas if c.get_text(strip=True)]
            if len(celdas_con_texto) < 3:
                continue
            celda_prog = celdas_con_texto[2]
            titulo, desc = extraer_titulo_y_desc(celda_prog)
            if not titulo:
                continue

            fin_fecha = fecha_madrid
            if re.search(r"PM", hora_inicio_txt, re.I) and re.search(r"AM", hora_fin_txt, re.I):
                fin_fecha = fecha_madrid + timedelta(days=1)

            inicio_dt = convertir_hora_a_espana(hora_inicio_txt, fecha_madrid, tz_espana)
            fin_dt = convertir_hora_a_espana(hora_fin_txt, fin_fecha, tz_espana)

            if not inicio_dt or not fin_dt:
                continue

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

    programas.sort(key=lambda x: x["inicio"])
    print(f"  ✓ {len(programas)} programas para {fecha_str}")
    return programas

def generar_xml(canales_data):
    tv = ET.Element("tv")
    tv.set("generator-info-name", "scraper_epg_fixed.py")
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
    pretty = dom.toprettyxml(indent="  ", encoding="UTF-8").decode("UTF-8")
    # Quitar lineas vacias de minidom
    pretty = "\n".join([l for l in pretty.split("\n") if l.strip()])
    return pretty

def main():
    print("═══ INICIANDO SCRAPER EPG GATOTV (FIXED) ═══")
    tz_espana = get_timezone_espana()

    # FIX CLAVE: hoy en hora de Madrid, no UTC
    hoy_madrid = datetime.now(TZ_MADRID).replace(hour=0, minute=0, second=0, microsecond=0)
    fechas = [hoy_madrid + timedelta(days=i) for i in range(DIAS)]
    print(f"Fechas a raspar (Madrid): {[f.strftime('%Y-%m-%d') for f in fechas]}")

    canales_data = []
    session = requests.Session()

    for canal in CANALES:
        print(f"\n─── Canal: {canal['nombre']} ───")
        todos_programas = []
        for fecha in fechas:
            programas_dia = raspar_canal_dia(canal["url_slug"], fecha, tz_espana, session)
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
