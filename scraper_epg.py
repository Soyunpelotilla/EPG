import requests, re, gzip, os
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET

URLS = [
    "https://cdn.epg.guru/7dayiptv/Mexico.xml",
    "https://cdn.epg.guru/7dayiptv/UnitedStates.xml",
]

# Solo ayer, hoy y mañana
hoy = datetime.now()
fechas_validas = {
    (hoy - timedelta(days=1)).strftime("%Y%m%d"),
    hoy.strftime("%Y%m%d"),
    (hoy + timedelta(days=1)).strftime("%Y%m%d"),
}

print(f"Filtrando solo: {fechas_validas}")

def arreglar_acentos(texto):
    if not texto: return texto
    if "Ã" in texto or "Â" in texto:
        try: texto = texto.encode('latin1').decode('utf-8')
        except: pass
    return texto

headers = {"User-Agent": "Mozilla/5.0"}
seen_channels = set()
total_prog = 0
total_filtrados = 0

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
                total_prog += 1
                if elem.get("start", "")[:8] in fechas_validas:
                    t = elem.find("title")
                    if t is not None and t.text: t.text = arreglar_acentos(t.text)
                    out.write(ET.tostring(elem, encoding="unicode") + "\n")
                    total_filtrados += 1
                elem.clear()
        os.remove(tmp)
    out.write('</tv>\n')

print(f"Total: {total_prog} -> Filtrados: {total_filtrados}")

with open("epg.xml", 'rb') as f_in:
    with gzip.open("epg.xml.gz", 'wb', compresslevel=9) as f_out:
        for chunk in iter(lambda: f_in.read(1024*1024), b''):
            f_out.write(chunk)

os.remove("epg.xml")
print(f"✓ epg.xml.gz ({os.path.getsize('epg.xml.gz')/1024/1024:.2f} MB)")
