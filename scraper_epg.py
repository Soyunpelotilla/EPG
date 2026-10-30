#!/usr/bin/env python3
# ==============================================================================
# Script: scraper_epg.py
# Función: Raspa programación de gatotv.com y genera XML en formato XMLTV
# Usa Playwright para ejecutar JavaScript y obtener la página completa.
# gatotv.com geolocaliza la IP → devuelve hora española directamente.
# ==============================================================================

from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
from xml.dom import minidom
from bs4 import BeautifulSoup
import re
import time

# ==============================================================================
# ZONA HORARIA ESPAÑA - Detección automática
# ==============================================================================

def ultimo_domingo(year, month):
    ultimo_dia = datetime(year, month + 1, 1) - timedelta(days=1) if month < 12 else datetime(year, 12, 31)
    dias_hasta_domingo = ultimo_dia.weekday() + 1
    if dias_hasta_domingo == 7:
        dias_hasta_domingo = 0
    return ultimo_dia - timedelta(days=dias_hasta_domingo)

def get_timezone_espana():
    ahora = datetime.utcnow()
    inicio_verano = ultimo_domingo(ahora.year, 3)
    fin_verano    = ultimo_domingo(ahora.year, 10)
    if inicio_verano <= ahora < fin_verano:
        offset, nombre = "+0200", "CEST (verano)"
    else:
        offset, nombre = "+0100", "CET (invierno)"
    print(f"  Zona horaria España detectada: {offset} ({nombre})")
    return offset

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
HORA_RE = re.compile(r"^\d{1,2}:\d{2}\s*(AM|PM)$", re.IGNORECASE)

# ==============================================================================
# FUNCIONES
# ==============================================================================

def convertir_hora(hora_str, fecha, tz_espana):
    """La web ya devuelve hora española. Solo parseamos y formateamos."""
    hora_str = hora_str.strip()
    try:
        t = datetime.strptime(hora_str, "%I:%M %p")
    except ValueError:
        return None
    dt = fecha.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
    return dt.strftime("%Y%m%d%H%M%S") + " " + tz_espana


def extraer_titulo_y_desc(celda):
    enlace = celda.find("a")
    if enlace:
        titulo = enlace.get_text(strip=True)
    else:
        lineas = [l.strip() for l in celda.get_text(separator="\n", strip=True).split("\n") if l.strip()]
        titulo = lineas[0] if lineas else ""

    desc = ""
    for tag in celda.find_all(["p", "span", "small"]):
        t = tag.get_text(strip=True)
        if t and t != titulo:
            desc = t
            break

    if not desc:
        lineas = [l.strip() for l in celda.get_text(separator="\n", strip=True).split("\n") if l.strip()]
        if len(lineas) > 1 and len(lineas[1]) > 30:
            desc = lineas[1]

    return titulo, desc


def raspar_canal_dia(page, slug, fecha, tz_espana):
    """Raspa un canal para una fecha usando Playwright (página ya renderizada)."""
    fecha_str = fecha.strftime("%Y-%m-%d")
    url = f"https://www.gatotv.com/canal/{slug}/{fecha_str}"
    print(f"  → Raspando: {url}")

    try:
        page.goto(url, wait_until="networkidle", timeout=30000)
        # Esperar a que aparezca la tabla de programación
        page.wait_for_selector("table", timeout=15000)
    except Exception as e:
        print(f"  ✗ Error cargando página: {e}")
        return []

    html = page.content()
    soup = BeautifulSoup(html, "html.parser")
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
            hora_fin_txt    = textos[1]

            if not HORA_RE.match(hora_inicio_txt):
                continue
            if not HORA_RE.match(hora_fin_txt):
                continue

            celdas_con_texto = [c for c in celdas if c.get_text(strip=True)]
            if len(celdas_con_texto) < 3:
                continue
            titulo, desc = extraer_titulo_y_desc(celdas_con_texto[2])

            if not titulo:
                continue

            # Cruce de medianoche: empieza PM y termina AM → fin es día siguiente
            fin_fecha = fecha
            if re.search(r"PM", hora_inicio_txt, re.I) and re.search(r"AM", hora_fin_txt, re.I):
                fin_fecha = fecha + timedelta(days=1)

            inicio_dt = convertir_hora(hora_inicio_txt, fecha, tz_espana)
            fin_dt    = convertir_hora(hora_fin_txt, fin_fecha, tz_espana)

            if not inicio_dt or not fin_dt:
                continue

            # Ignorar programas con duración cero
            if inicio_dt == fin_dt:
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


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    print("═══ INICIANDO SCRAPER EPG GATOTV (Playwright) ═══")
    tz_espana = get_timezone_espana()

    hoy = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    fechas = [hoy + timedelta(days=i) for i in range(DIAS)]

    canales_data = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            locale="es-ES",
            timezone_id="Europe/Madrid",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        page = context.new_page()

        for canal in CANALES:
            print(f"\n─── Canal: {canal['nombre']} ───")
            todos_programas = []

            for fecha in fechas:
                programas_dia = raspar_canal_dia(page, canal["url_slug"], fecha, tz_espana)
                todos_programas.extend(programas_dia)
                time.sleep(1)

            canales_data.append({
                "id": canal["id"],
                "nombre": canal["nombre"],
                "logo": canal["logo"],
                "programas": todos_programas,
            })
            print(f"  ═► Total: {len(todos_programas)} programas en {DIAS} días")

        browser.close()

    print("\n─── GENERANDO XML ───")
    xml_output = generar_xml(canales_data)

    with open("guide.xml", "w", encoding="UTF-8") as f:
        f.write(xml_output)

    total = sum(len(c["programas"]) for c in canales_data)
    print(f"✓ guide.xml generado — Canales: {len(canales_data)} | Programas: {total}")
    print("═══ PROCESO FINALIZADO ═══")


if __name__ == "__main__":
    main()
