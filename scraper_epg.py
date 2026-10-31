#!/usr/bin/env python3
# scraper_hoy_playwright_direct - FIX para GitHub
# Siempre usa fecha de Madrid, no UTC de GitHub

from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET
from xml.dom import minidom
from bs4 import BeautifulSoup
import time

MADRID = ZoneInfo("Europe/Madrid")

def get_offset_espana():
    ahora = datetime.now(MADRID)
    def ultimo_domingo(y,m):
        if m==12:
            u=datetime(y,12,31)
        else:
            u=datetime(y,m+1,1)-timedelta(days=1)
        while u.weekday()!=6:
            u-=timedelta(days=1)
        return u
    inicio = ultimo_domingo(ahora.year,3)
    fin = ultimo_domingo(ahora.year,10)
    # Comparar solo fecha
    hoy0 = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    inicio0 = inicio.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=MADRID)
    fin0 = fin.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=MADRID)
    if inicio0 <= hoy0 < fin0:
        return "+0200"
    else:
        return "+0100"

CANALES = [
    {"id": "FOX MX", "nombre": "FOX MX", "url_slug": "fox_mexico", "logo": "https://imagenes.gatotv.com/logos/canales/oscuros/fox-mediano.png"},
    {"id": "FOX+ MX", "nombre": "FOX+ MX", "url_slug": "fox_plus_centroamerica", "logo": "https://imagenes.gatotv.com/logos/canales/oscuros/fox_plus-mediano.png"},
    {"id": "Canal 5 MX", "nombre": "Canal 5 MX", "url_slug": "5_mexico", "logo": "https://imagenes.gatotv.com/logos/canales/oscuros/5_de_mexico-mediano.png"},
]

def parse_hora_es(txt):
    txt=txt.strip()
    for fmt in ("%H:%M", "%I:%M %p", "%I:%M%p"):
        try:
            return datetime.strptime(txt.upper().replace(".", ""), fmt)
        except:
            continue
    return None

def raspar_hoy(page, slug, fecha_hoy, tz_offset):
    url = f"https://www.gatotv.com/canal/{slug}"
    print(f"  → {url} (fecha Madrid: {fecha_hoy.strftime('%Y-%m-%d')})")
    page.goto(url, wait_until="networkidle", timeout=30000)
    page.wait_for_selector("table.tbl_EPG", timeout=15000)
    # Pequeña espera extra para que el JS convierta la hora
    page.wait_for_timeout(1500)
    html = page.content()
    soup = BeautifulSoup(html, "html.parser")
    progs=[]
    vistos=set()
    for tr in soup.find_all("tr"):
        times=tr.find_all("time")
        if len(times)<2:
            continue
        h_ini=(times[0].get("datetime") or times[0].get_text()).strip()
        h_fin=(times[1].get("datetime") or times[1].get_text()).strip()
        div=tr.find("div", class_="div_program_title_on_channel")
        if not div:
            continue
        titulo=div.get_text(strip=True)
        if not titulo:
            continue

        t_ini=parse_hora_es(h_ini)
        t_fin=parse_hora_es(h_fin)
        if not t_ini or not t_fin:
            continue

        fecha_fin=fecha_hoy
        if t_ini.hour>=18 and t_fin.hour<=6:
            fecha_fin=fecha_hoy+timedelta(days=1)

        dt_ini=fecha_hoy.replace(hour=t_ini.hour, minute=t_ini.minute, second=0, microsecond=0)
        dt_fin=fecha_fin.replace(hour=t_fin.hour, minute=t_fin.minute, second=0, microsecond=0)

        ini_str=dt_ini.strftime("%Y%m%d%H%M%S")+f" {tz_offset}"
        fin_str=dt_fin.strftime("%Y%m%d%H%M%S")+f" {tz_offset}"

        clave=f"{ini_str}|{titulo}"
        if clave in vistos:
            continue
        vistos.add(clave)
        progs.append({"titulo":titulo,"inicio":ini_str,"fin":fin_str,"dt":dt_ini})

    progs.sort(key=lambda x:x["dt"])
    print(f"  ✓ {len(progs)} programas HOY (hora España directa)")
    return progs

def generar_xml(data):
    tv=ET.Element("tv")
    for c in data:
        ch=ET.SubElement(tv,"channel")
        ch.set("id",c["id"])
        ET.SubElement(ch,"display-name").text=c["nombre"]
    for c in data:
        for p in c["programas"]:
            pr=ET.SubElement(tv,"programme")
            pr.set("start",p["inicio"])
            pr.set("stop",p["fin"])
            pr.set("channel",c["id"])
            t=ET.SubElement(pr,"title")
            t.set("lang","es")
            t.text=p["titulo"]
    xml=ET.tostring(tv,encoding="unicode")
    return minidom.parseString(xml).toprettyxml(indent="  ",encoding="UTF-8").decode("UTF-8")

def main():
    tz_offset=get_offset_espana()
    ahora_madrid = datetime.now(MADRID)
    ahora_utc = datetime.utcnow()
    # FIX: hoy SIEMPRE en Madrid, no en UTC de GitHub
    hoy = ahora_madrid.replace(hour=0,minute=0,second=0,microsecond=0)
    print(f"GitHub UTC: {ahora_utc} | Madrid: {ahora_madrid} | Hoy para XML: {hoy} | Offset: {tz_offset}")
    print(f"Si en España es 01:35 del 31, en México son 18:35 del 30, pero pedimos el 31 de España")
    
    canales_data=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        context=browser.new_context(
            locale="es-ES",
            timezone_id="Europe/Madrid",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        )
        page=context.new_page()
        for canal in CANALES:
            print(f"\n--- {canal['nombre']} ---")
            progs=raspar_hoy(page,canal["url_slug"],hoy,tz_offset)
            canales_data.append({**canal,"programas":progs})
            time.sleep(1)
        browser.close()
    xml=generar_xml(canales_data)
    open("guide.xml","w",encoding="UTF-8").write(xml)
    print(f"✓ guide.xml {sum(len(c['programas']) for c in canales_data)} programas en hora España")

if __name__=="__main__":
    main()
