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
# DETECCIÓN DE ZONA HORARIA DE LA WEB
# Raspa un programa de hoy, lo compara con la hora UTC actual y deduce el offset
# ==============================================================================

OFFSETS_CONOCIDOS = {
    -8: "-0800",  # PST (Pacífico)
    -7: "-0700",  # MST (Montaña)
    -6: "-0600",  # CST (México Centro) ← el más probable
    -5: "-0500",  # EST (México Este / Colombia)
    0:  "+0000",  # UTC (GitHub Actions por defecto)
    1:  "+0100",  # CET (España invierno)
    2:  "+0200",  # CEST (España verano)
}

def detectar_tz_web():
    """
    Detecta en qué zona horaria está devolviendo las horas gatotv.com.

    Estrategia:
      1. Raspa la página de hoy de un canal de referencia.
      2. Recoge TODAS las horas de los programas (AM/PM).
      3. Convierte cada hora a minutos desde medianoche.
      4. Calcula la hora UTC actual también en minutos.
      5. Para cada offset conocido, comprueba si alguna hora raspada
         encaja con "ahora ± 30 min" al restar el offset.
      6. El offset con más coincidencias gana.

    Devuelve el offset como string (p.ej. "-0600") o None si no se detecta.
    """
    print("\n─── DETECTANDO ZONA HORARIA DE LA WEB ───")

    slug_prueba = "fox_mexico"
    hoy = datetime.utcnow()
    fecha_str = hoy.strftime("%Y-%m-%d")
    url = f"https://www.gatotv.com/canal/{slug_prueba}/{fecha_str}"
    print(f"  URL de prueba: {url}")
    print(f"  Hora UTC actual: {hoy.strftime('%H:%M')}")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"  ✗ No se pudo conectar para detectar TZ: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    hora_re = re.compile(r"^\d{1,2}:\d{2}\s*(AM|PM)$", re.IGNORECASE)

    horas_raspadas = []
    for tabla in soup.find_all("table"):
        for fila in tabla.find_all("tr"):
            celdas = fila.find_all("td")
            textos = [c.get_text(separator=" ", strip=True) for c in celdas]
            textos = [t for t in textos if t]
            if len(textos) >= 2 and hora_re.match(textos[0]):
                horas_raspadas.append(textos[0])

    if not horas_raspadas:
        print("  ✗ No se encontraron horas en la página.")
        return None

    print(f"  Horas encontradas en la web ({len(horas_raspadas)}): {horas_raspadas[:8]}{'...' if len(horas_raspadas) > 8 else ''}")

    # Convertir horas raspadas a minutos desde medianoche
    def hora_a_minutos(hora_str):
        try:
            t = datetime.strptime(hora_str.strip(), "%I:%M %p")
            return t.hour * 60 + t.minute
        except ValueError:
            return None

    minutos_raspados = [hora_a_minutos(h) for h in horas_raspadas]
    minutos_raspados = [m for m in minutos_raspados if m is not None]

    # Minutos UTC actuales
    minutos_utc = hoy.hour * 60 + hoy.minute

    # Para cada offset, contar cuántas horas raspadas corresponden a "ahora"
    VENTANA = 60  # ± 60 minutos alrededor de la hora actual
    scores = {}
    for offset_h, offset_str in OFFSETS_CONOCIDOS.items():
        minutos_web = (minutos_utc + offset_h * 60) % (24 * 60)
        coincidencias = sum(
            1 for m in minutos_raspados
            if abs(m - minutos_web) <= VENTANA or abs(m - minutos_web - 1440) <= VENTANA
        )
        scores[offset_str] = coincidencias
        print(f"    Offset {offset_str}: hora esperada = {minutos_web // 60:02d}:{minutos_web % 60:02d} → {coincidencias} coincidencias")

    mejor_offset = max(scores, key=scores.get)
    mejor_score  = scores[mejor_offset]

    if mejor_score == 0:
        print("  ✗ No se pudo determinar el offset con certeza.")
        return None

    print(f"\n  ✔ Zona horaria detectada de la web: {mejor_offset} (score: {mejor_score})")
    return mejor_offset


# ==============================================================================
# CONFIGURACIÓN - Añade o quita canales aquí
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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "es-MX,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

HORA_RE = re.compile(r"^\d{1,2}:\d{2}\s*(AM|PM)$", re.IGNORECASE)

# ==============================================================================
# FUNCIONES
# ==============================================================================

def convertir_hora(hora_str, fecha, tz_web, tz_espana):
    """
    Convierte una hora de la web (en tz_web) a hora de España (tz_espana).
    Devuelve formato XMLTV: 'YYYYMMDDHHMMSS +0100'
    """
    hora_str = hora_str.strip()
    try:
        t = datetime.strptime(hora_str, "%I:%M %p")
    except ValueError:
        return None

    dt_local = fecha.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)

    # Convertir a UTC restando el offset de la web
    offset_web_h = int(tz_web[:3])   # p.ej. -6 para "-0600"
    dt_utc = dt_local - timedelta(hours=offset_web_h)

    # Convertir a hora España sumando su offset
    offset_espana_h = int(tz_espana[:3])  # +1 o +2
    dt_espana = dt_utc + timedelta(hours=offset_espana_h)

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


def raspar_canal_dia(slug, fecha, tz_web, tz_espana):
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

            # Fecha de fin (si empieza PM y termina AM → día siguiente)
            fin_fecha = fecha
            if re.search(r"PM", hora_inicio_txt, re.I) and re.search(r"AM", hora_fin_txt, re.I):
                fin_fecha = fecha + timedelta(days=1)

            inicio_dt = convertir_hora(hora_inicio_txt, fecha, tz_web, tz_espana)
            fin_dt    = convertir_hora(hora_fin_txt, fin_fecha, tz_web, tz_espana)

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

    # 1. Detectar zona horaria de España
    tz_espana = get_timezone_espana()

    # 2. Detectar zona horaria que usa la web según nuestra IP
    tz_web = detectar_tz_web()
    if tz_web is None:
        tz_web = "-0600"  # Fallback: México Centro
        print(f"  ⚠ Usando zona horaria por defecto: {tz_web} (México Centro)")
    print(f"\n  RESUMEN: web en {tz_web} → convertir a España {tz_espana}")

    hoy = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    fechas = [hoy + timedelta(days=i) for i in range(DIAS)]

    canales_data = []

    for canal in CANALES:
        print(f"\n─── Canal: {canal['nombre']} ───")
        todos_programas = []

        for fecha in fechas:
            programas_dia = raspar_canal_dia(canal["url_slug"], fecha, tz_web, tz_espana)
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
