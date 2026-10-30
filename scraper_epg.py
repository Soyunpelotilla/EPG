#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET
from xml.dom import minidom
import time, re
TZ_MADRID = ZoneInfo("Europe/Madrid")
TZ_MEXICO_OFFSET = 7
print(f"═══ SCRAPER OFFSET {TZ_MEXICO_OFFSET}h - PANTHERS 01:00 ES ═══")
CANALES=[
 {"id":"FOX MX","nombre":"FOX MX","url_slug":"fox_mexico","logo":"https://imagenes.gatotv.com/logos/canales/oscuros/fox-mediano.png"},
 {"id":"FOX+ MX","nombre":"FOX+ MX","url_slug":"fox_plus_centroamerica","logo":"https://imagenes.gatotv.com/logos/canales/oscuros/fox_plus-mediano.png"},
 {"id":"Canal 5 MX","nombre":"Canal 5 MX","url_slug":"5_mexico","logo":"https://imagenes.gatotv.com/logos/canales/oscuros/5_de_mexico-mediano.png"},
]
HEADERS={"User-Agent":"Mozilla/5.0 Chrome/120"}
HORA_RE=re.compile(r"^\d{1,2}:\d{2}$",re.IGNORECASE)
def convertir_hora(hora_str, fecha_base):
    t=datetime.strptime(hora_str.strip(),"%H:%M")
    fecha_mx=datetime(fecha_base.year,fecha_base.month,fecha_base.day,t.hour,t.minute)
    dt_utc=fecha_mx+timedelta(hours=TZ_MEXICO_OFFSET)
    dt_utc=dt_utc.replace(tzinfo=ZoneInfo("UTC"))
    return dt_utc.astimezone(TZ_MADRID).strftime("%Y%m%d%H%M%S %z")
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
        tds=[c.get_text(strip=True) for c in tr.find_all("td") if c.get_text(strip=True)]
        if len(tds)<2: continue
        # GatoTV muestra formato 24h ej: "10:00" y "- " y "12:00"
        horas_encontradas = []
        for td in tds:
            m = re.findall(r"^\d{1,2}:\d{2}$", td)
            if m:
                horas_encontradas.extend(m)
        if len(horas_encontradas) < 2:
            # Intentar buscar por filas o celdas de texto exacto de hora
            continue
        # Tomar la primera y segunda hora como inicio y fin
        hora_ini = horas_encontradas[0]
        hora_fin = horas_encontradas[1]
        
        celdas=[c for c in tr.find_all("td") if c.get_text(strip=True)]
        if len(celdas)<3: continue
        titulo=celdas[2].find("a").get_text(strip=True) if celdas[2].find("a") else celdas[2].get_text(strip=True).split("\n")[0]
        titulo=titulo.strip()
        fin_fecha=fecha+timedelta(days=1) if hora_ini > hora_fin else fecha
        ini=convertir_hora(hora_ini,fecha)
        fin=convertir_hora(hora_fin,fin_fecha)
        if ini and fin:
            progs.append({"titulo":titulo,"inicio":ini,"fin":fin})
    progs.sort(key=lambda x:x["inicio"])
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
    tv.set("generator-info-name",f"scraper_epg.py OFFSET {TZ_MEXICO_OFFSET}h")
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
    print(f"✓ guide.xml OFFSET {TZ_MEXICO_OFFSET}h generado")
if __name__=="__main__": main()
