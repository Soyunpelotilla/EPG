#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET
from xml.dom import minidom
import time, re
TZ_MADRID = ZoneInfo("Europe/Madrid")
TZ_MEXICO_OFFSET = 0
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
    
    # GatoTV organiza la programación en filas <tr> dentro de las tablas de horarios
    for tr in soup.find_all("tr"):
        # Buscamos celdas con la clase o estructura de hora y programa
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
            
        # Extraer texto de todas las celdas de la fila
        textos_tds = [td.get_text(separator=" ", strip=True) for td in tds]
        
        # Buscamos si hay horas en formato HH:MM en la fila
        horas_en_fila = []
        for txt in textos_tds:
            m = re.findall(r"\b(\d{2}:\d{2})\b", txt)
            if m:
                horas_en_fila.extend(m)
                
        if len(horas_en_fila) < 2:
            continue
            
        hora_ini = horas_en_fila[0]
        hora_fin = horas_en_fila[1]
        
        # El título del programa suele estar en la celda del medio (índice 1 o 2) o en un enlace <a>
        titulo = ""
        for td in tds:
            # Ignoramos celdas que sean solo horas o guiones
            txt_c = " ".join(td.get_text(separator=" ", strip=True).split())
            if re.match(r"^\d{2}:\d{2}$", txt_c) or txt_c == "-" or not txt_c:
                continue
            
            # Buscar enlace o texto principal
            a_tag = td.find("a")
            if a_tag and a_tag.get_text(strip=True):
                titulo = a_tag.get_text(strip=True)
            else:
                # Tomamos la primera línea de texto limpio de la celda
                titulo = txt_c.split("\n")[0]
            break
            
        titulo = " ".join(titulo.split())
        if not titulo or "Horarios para" in titulo or re.match(r"^\d{2}:\d{2}", titulo):
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
