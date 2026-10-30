#!/usr/bin/env python3
# ==============================================================================
# Script: scraper_epg.py
# Función: Raspa programación de gatotv.com y genera XML en formato XMLTV
# Zona horaria: España (UTC+1 invierno / UTC+2 verano), detectada automáticamente
# ==============================================================================

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
from xml.dom import minidom
import time
import re

# ==============================================================================
# ZONA HORARIA ESPAÑA - Detección automática
# Cambio de hora: último domingo de marzo (→ +0200) y octubre (→ +0100)
# ==============================================================================

def ultimo_domingo(year, month):
    """Devuelve la fecha del último domingo de un mes dado."""
    ultimo_dia = datetime(year, month + 1, 1) - timedelta(days=1) if month < 12 else datetime(year, 12, 31)
    dias_hasta_domingo = ultimo_dia.weekday() + 1  # weekday(): lunes=0, domingo=6
    if dias_hasta_domingo == 7:
        dias_hasta_domingo = 0
    return ultimo_dia - timedelta(days=dias_hasta_domingo)

def get_timezone_espana():
    """
    Devuelve el offset de España según la fecha actual.
    Verano (CEST): último domingo de marzo → último domingo de octubre → +0200
    Invierno (CET): resto del año → +0100
    """
    ahora = datetime.utcnow()
    inicio_verano = ultimo_domingo(ahora.year, 3)   # Último domingo de marzo
    fin_verano    = ultimo_domingo(ahora.year, 10)  # Último domingo de octubre

    if inicio_verano <= ahora < fin_verano:
        offset = "+0200"
        nombre = "CEST (verano)"
    else:
        offset = "+0100"
        nombre = "CET (invierno)"

    print(f"  Zona horaria España detectada: {offset} ({nombre})")
    return offset

# ==============================================================================
# CONFIGURACIÓN - Añade o quita canales aquí
# ==============================================================================

TZ_MEXICO = "-0600"   # Hora en que la web publica los horarios (México Centro)

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

HORA_RE = re.compile(r"^\d{1,2}:\d{2}$", re.IGNORECASE)

# ==============================================================================
# FUNCIONES
# ==============================================================================

def convertir_hora_a_espana(hora_str, fecha, tz_espana):
    """
    Usa directamente la hora de GatoTV (en formato 24h) con su offset.
    """
    hora_str = hora_str.strip()
    try:
        t = datetime.strptime(hora_str, "%H:%M")
    except ValueError:
        return None

    dt_espana = fecha.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
    return dt_espana.strftime("%Y%m%d%H%M%S") + " " + tz_espana


def extraer_titulo_y_desc(celda):
    """Extrae título y descripción de la celda del programa."""
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

    if not desc:
        texto_completo = celda.get_text(separator="\n", strip=True)
        lineas = [l.strip() for l in texto_completo.split("\n") if l.strip()]
        if len(lineas) > 1 and len(lineas[1]) > 30:
            desc = lineas[1]

    return titulo, desc


def raspar_canal_dia(slug, fecha, tz_espana):
    """Raspa los programas de un canal para una fecha concreta."""
    fecha_str = fecha.strftime("%Y-%m-%d")
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

    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
            
        horas_en_fila = []
        for td in tds:
            txt_td = td.get_text(separator=" ", strip=True)
            m = re.findall(r"\b(\d{2}:\d{2})\b", txt_td)
            if m:
                horas_en_fila.extend(m)
                
        if len(horas_en_fila) < 2:
            continue
            
        hora_ini = horas_en_fila[0]
        hora_fin = horas_en_fila[1]
        
        titulo = ""
        for td in tds:
            txt_c = td.get_text(separator=" ", strip=True)
            if re.match(r"^\d{2}:\d{2}$", txt_c) or txt_c == "-" or not txt_c or "Horarios para" in txt_c:
                continue
            a_tag = td.find("a")
            if a_tag and a_tag.get_text(strip=True):
                titulo = a_tag.get_text(strip=True)
                break
            else:
                lineas = [l.strip() for l in td.get_text(separator="\n", strip=True).split("\n") if l.strip()]
                lineas_validas = [l for l in lineas if not re.match(r"^\d{2}:\d{2}$", l) and l != "-"]
                if lineas_validas:
                    titulo = lineas_validas[0]
                    break
                    
        titulo = " ".join(titulo.split())
        if not titulo or "Horarios de Programación" in titulo or "Horarios para" in titulo:
            continue
            
        fin_fecha = fecha + timedelta(days=1) if hora_ini > hora_fin else fecha
        inicio_dt = convertir_hora_a_espana(hora_ini, fecha, tz_espana)
        fin_dt = convertir_hora_a_espana(hora_fin, fin_fecha, tz_espana)

        if not inicio_dt or not fin_dt:
            continue

        clave = f"{inicio_dt}|{titulo}"
        if clave in vistos:
            continue
        vistos.add(clave)

        programas.append({
            "titulo": titulo,
            "desc": "",
            "inicio": inicio_dt,
            "fin": fin_dt,
        })

    print(f"  ✓ {len(programas)} programas para {fecha_str}")
    return programas


def generar_xml(canales_data):
    """Genera el XML en formato XMLTV."""
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
    print("═══ INICIANDO SCRAPER EPG GATOTV ═══")

    # Detectar zona horaria de España automáticamente
    tz_espana = get_timezone_espana()

    hoy = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    fechas = [hoy + timedelta(days=i) for i in range(DIAS)]

    canales_data = []

    for canal in CANALES:
        print(f"\n─── Canal: {canal['nombre']} ───")
        todos_programas = []

        for fecha in fechas:
            programas_dia = raspar_canal_dia(canal["url_slug"], fecha, tz_espana)
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
