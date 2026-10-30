#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET
from xml.dom import minidom
import time, re

TZ_MADRID = ZoneInfo("Europe/Madrid")
print("═══ SCRAPER EPG GATOTV - HORA ESPAÑA DIRECTА ═══")

CANALES=[
 {"id":"FOX MX","nombre":"FOX MX","url_slug":"fox_mexico","logo":"https://imagenes.gatotv.com/logos/canales/oscuros/fox-mediano.png"},
 {"id":"FOX+ MX","nombre":"FOX+ MX","url_slug":"fox_plus_centroamerica","logo":"https://imagenes.gatotv.com/logos/canales/oscuros/fox_plus-mediano.png"},
 {"id":"Canal 5 MX","nombre":"Canal 5 MX","url_slug":"5_mexico","logo":"https://imagenes.gatotv.com/logos/canales/oscuros/5_de_mexico-mediano.png"},
]

HEADERS={"User-Agent":"Mozilla/5.0 Chrome/120"}
HORA_RE=re.compile(r"^\d{1,2}:\d{2}$",re.IGNORECASE)

def convertir_hora(hora_str, fecha_base):
    t = datetime.strptime(hora_str.strip(), "%H:%M")
    dt_local = datetime(fecha_base.year, fecha_base.month, fecha_base.day, t.hour, t.minute, tzinfo=TZ_MADRID)
    return dt_local.strftime("%Y%m%d%H%M%S %z")

def raspar(slug, fecha, session):
    url=f"https://www.gatotv.com/canal/{slug}/{fecha.strftime('%Y-%m-%d')}"
    try:
        r=session.get(url,headers=HEADERS,timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"✗ {e}")
        return []
    soup=BeautifulSoup(r.text,"html.parser")
    progs=[]
    
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
            if re.match(r"^\d{1,2}:\d{2}$", txt_c) or txt_c == "-" or not txt_c or "Horarios para" in txt_c:
                continue
                
            a_tag = td.find("a")
            if a_tag and a_tag.get_text(strip=True):
                titulo = a_tag.get_text(strip=True)
                break
            else:
                lineas = [l.strip() for l in td.get_text(separator="\n", strip=True).split("\n") if l.strip()]
                lineas_validas = [l for l in lineas if not re.match(r"^\d{1,2}:\d{2}$", l) and l != "-"]
                if lineas_validas:
                    titulo = lineas_validas[0]
                    break
                    
        titulo = " ".join(titulo.split())
        # Evitar que el título sea una hora o texto de cabecera
        if not titulo or re.match(r"^\d{1,2}:\d{2}$", titulo) or "Horarios de Programación" in titulo or "Horarios para" in titulo:
            continue
            
        fin_fecha = fecha + timedelta(days=1) if hora_ini > hora_fin else fecha
        ini = convertir_hora(hora_ini, fecha)
        fin = convertir_hora(hora_fin, fin_fecha)
        if ini and fin:
            progs.append({"titulo": titulo, "inicio": ini, "fin": fin})
            
    progs.sort(key=lambda x: x["inicio"])
    return progs

def main():
    hoy=datetime.now(TZ_MADRID).replace(hour=0,minute=0,second=0,microsecond=0)
    fechas=[hoy+timedelta(days=i) for i in range(-1,3)]
    print(f"Fechas Madrid: {[f.strftime('%Y-%m-%d') for f in fechas]}")
    session=requests.Session()
    all_data=[]
    for canal in CANALES:
        todos=[]
        for f in fechas:
            todos.extend(raspar(canal["url_slug"],f,session))
            time.sleep(0.6)
        uniq={}
        for p in sorted(todos,key=lambda x:x["inicio"]):
            uniq[f"{p['inicio']}|{p['titulo']}"]=p
        all_data.append({**canal,"programas":list(uniq.values())})
    tv=ET.Element("tv")
    tv.set("generator-info-name","scraper_epg.py (Hora España directa)")
    for c in all_data:
        ch=ET.SubElement(tv,"channel")
        ch.set("id",c["id"])
        ET.SubElement(ch,"display-name").text=c["nombre"]
        if c.get("logo"): ET.SubElement(ch,"icon").set("src",c["logo"])
    for c in all_data:
        for p in sorted(c["programas"],key=lambda x:x["inicio"]):
            pr=ET.SubElement(tv,"programme")
            pr.set("start",p["inicio"])
            pr.set("stop",p["fin"])
            pr.set("channel",c["id"])
            ET.SubElement(pr,"title",lang="es").text=p["titulo"]
    xml_str=ET.tostring(tv,encoding="unicode")
    pretty=minidom.parseString(xml_str).toprettyxml(indent="  ",encoding="UTF-8").decode("UTF-8")
    pretty="\n".join([l for l in pretty.split("\n") if l.strip()])
    open("guide.xml","w",encoding="UTF-8").write(pretty)
    print("✓ guide.xml generado con hora directa de España")

if __name__=="__main__": main()
