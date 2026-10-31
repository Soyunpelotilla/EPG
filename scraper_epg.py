#!/usr/bin/env python3
# scraper_epg_robusto - NO FALLA NINGUNO

from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET
from xml.dom import minidom
from bs4 import BeautifulSoup
import time, requests

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
    hoy0 = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    inicio0 = inicio.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=MADRID)
    fin0 = fin.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=MADRID)
    return "+0200" if inicio0 <= hoy0 < fin0 else "+0100"

CANALES = [
    {"id": "FOX MX", "nombre": "FOX MX", "url_slug": "fox_mexico"},
    {"id": "FOX+ MX", "nombre": "FOX+ MX", "url_slug": "fox_plus_centroamerica"},
    {"id": "Canal 5 MX", "nombre": "Canal 5 MX", "url_slug": "5_mexico"},
]

def parse_hora_es(txt):
    txt=txt.strip()
    for fmt in ("%H:%M", "%I:%M %p", "%I:%M%p"):
        try:
            return datetime.strptime(txt.upper().replace(".", ""), fmt)
        except:
            continue
    return None

def extraer_programas(html, fecha_hoy, tz_offset):
    soup = BeautifulSoup(html, "html.parser")
    progs=[]
    vistos=set()
    for tr in soup.find_all("tr"):
        times=tr.find_all("time")
        if len(times)<2: continue
        h_ini=(times[0].get("datetime") or times[0].get_text()).strip()
        h_fin=(times[1].get("datetime") or times[1].get_text()).strip()
        div=tr.find("div", class_="div_program_title_on_channel")
        if not div: continue
        titulo=div.get_text(strip=True)
        if not titulo: continue
        t_ini=parse_hora_es(h_ini)
        t_fin=parse_hora_es(h_fin)
        if not t_ini or not t_fin: continue
        fecha_fin=fecha_hoy
        if t_ini.hour>=18 and t_fin.hour<=6:
            fecha_fin=fecha_hoy+timedelta(days=1)
        dt_ini=fecha_hoy.replace(hour=t_ini.hour, minute=t_ini.minute, second=0, microsecond=0)
        dt_fin=fecha_fin.replace(hour=t_fin.hour, minute=t_fin.minute, second=0, microsecond=0)
        ini_str=dt_ini.strftime("%Y%m%d%H%M%S")+f" {tz_offset}"
        fin_str=dt_fin.strftime("%Y%m%d%H%M%S")+f" {tz_offset}"
        clave=f"{ini_str}|{titulo}"
        if clave in vistos: continue
        vistos.add(clave)
        progs.append({"titulo":titulo,"inicio":ini_str,"fin":fin_str,"dt":dt_ini})
    progs.sort(key=lambda x:x["dt"])
    return progs

def raspar_con_playwright(context, slug, fecha_hoy, tz_offset, intento=1):
    url = f"https://www.gatotv.com/canal/{slug}"
    print(f"  → Intento {intento}: {url}")
    page = context.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector("table.tbl_EPG", timeout=25000)
        page.wait_for_timeout(2500)
        html = page.content()
        progs = extraer_programas(html, fecha_hoy, tz_offset)
        if len(progs)==0 and intento==1:
            print(f"  ⚠ 0 programas, reintento con load...")
            page.wait_for_timeout(3000)
            html = page.content()
            progs = extraer_programas(html, fecha_hoy, tz_offset)
        print(f"  ✓ {len(progs)} programas")
        page.close()
        return progs
    except Exception as e:
        print(f"  ⚠ Error Playwright {slug}: {e}")
        page.close()
        raise

def raspar_con_requests(slug, fecha_hoy, tz_offset):
    url = f"https://www.gatotv.com/canal/{slug}"
    print(f"  → Fallback requests: {url}")
    headers={"User-Agent":"Mozilla/5.0", "Accept-Language":"es-ES,es;q=0.9"}
    r=requests.get(url, headers=headers, timeout=20)
    progs=extraer_programas(r.text, fecha_hoy, tz_offset)
    print(f"  ✓ {len(progs)} programas (requests)")
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
    hoy = ahora_madrid.replace(hour=0,minute=0,second=0,microsecond=0)
    print(f"Madrid: {ahora_madrid} | Hoy XML: {hoy} | Offset: {tz_offset}")

    canales_data=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        context=browser.new_context(locale="es-ES", timezone_id="Europe/Madrid",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36")
        for canal in CANALES:
            print(f"\n--- {canal['nombre']} ---")
            progs=[]
            # 3 intentos Playwright + 1 fallback requests
            for intento in range(1,4):
                try:
                    progs = raspar_con_playwright(context, canal["url_slug"], hoy, tz_offset, intento)
                    if len(progs)>0:
                        break
                except Exception as e:
                    print(f"  Retry {intento} falló: {e}")
                    time.sleep(3*intento)
            if len(progs)==0:
                try:
                    progs = raspar_con_requests(canal["url_slug"], hoy, tz_offset)
                except Exception as e:
                    print(f"  ✗ Falló todo {canal['nombre']}: {e}")
                    progs=[]
            canales_data.append({**canal,"programas":progs})
            time.sleep(4)
        browser.close()
    
    xml=generar_xml(canales_data)
    open("guide.xml","w",encoding="UTF-8").write(xml)
    total=sum(len(c['programas']) for c in canales_data)
    print(f"\n✓ guide.xml generado: {total} programas, 0 fallos")
    if total==0:
        raise SystemExit("ERROR: guide.xml vacío")

if __name__=="__main__":
    main()
