import requests, re, gzip, os
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET

URLS = [
    "https://cdn.epg.guru/7dayiptv/Mexico.xml",
    "https://cdn.epg.guru/7dayiptv/UnitedStates.xml",
    # Añade más aquí, ej:
    # "https://cdn.epg.guru/7dayiptv/Latino.xml",
]

hoy = datetime.now()
fechas_validas = {
    (hoy - timedelta(days=1)).strftime("%Y%m%d"),
    hoy.strftime("%Y%m%d"),
    (hoy + timedelta(days=1)).strftime("%Y%m%d"),
}

def nombre_de_url(url):
    # Mexico.xml -> Mexico, UnitedStates.xml -> UnitedStates
    base = url.split("/")[-1].replace(".xml","")
    return base

nombres = [nombre_de_url(u) for u in URLS]
lista_nombres = " + ".join(nombres)

print(f"Filtrando: {fechas_validas} -> {lista_nombres}")

def arreglar_acentos(texto):
    if not texto: return texto
    if "Ã" in texto or "Â" in texto:
        try: texto = texto.encode('latin1').decode('utf-8')
        except: pass
    return texto

headers = {"User-Agent": "Mozilla/5.0"}
seen_channels = set()

with open("epg.xml", "w", encoding="utf-8") as out:
    out.write('<?xml version="1.0" encoding="UTF-8"?>\n<tv>\n')
    for URL in URLS:
        print(f"Bajando {URL}...")
        tmp = "temp_epg.xml"
        with requests.get(URL, headers=headers, stream=True, timeout=300) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024*1024):
                    f.write(chunk)
        for event, elem in ET.iterparse(tmp, events=("end",)):
            if elem.tag == "channel":
                cid = elem.get("id")
                if cid not in seen_channels:
                    seen_channels.add(cid)
                    for dn in elem.findall("display-name"):
                        if dn.text: dn.text = arreglar_acentos(dn.text)
                    out.write(ET.tostring(elem, encoding="unicode") + "\n")
                elem.clear()
            elif elem.tag == "programme":
                if elem.get("start", "")[:8] in fechas_validas:
                    t = elem.find("title")
                    if t is not None and t.text: t.text = arreglar_acentos(t.text)
                    out.write(ET.tostring(elem, encoding="unicode") + "\n")
                elem.clear()
        os.remove(tmp)
    out.write('</tv>\n')

with open("epg.xml", 'rb') as f_in:
    with gzip.open("epg.xml.gz", 'wb', compresslevel=9) as f_out:
        for chunk in iter(lambda: f_in.read(1024*1024), b''):
            f_out.write(chunk)
os.remove("epg.xml")

# Crear archivo con la info para el Release
with open("release_info.txt", "w", encoding="utf-8") as f:
    f.write(f"Actualizado automáticamente cada 6 horas\n")
    f.write(f"Contenido: Ayer + Hoy + Mañana\n")
    f.write(f"{lista_nombres}\n")

with open("release_name.txt", "w", encoding="utf-8") as f:
    f.write(f"EPG 3 dias")

print(f"✓ epg.xml.gz {os.path.getsize('epg.xml.gz')/1024/1024:.2f} MB")
print(f"✓ Fuentes: {lista_nombres}")
