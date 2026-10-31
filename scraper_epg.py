import requests
import re
import gzip
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime, timedelta

# AQUI AÑADES MAS URL SI QUIERES
URLS = [
    "https://cdn.epg.guru/7dayiptv/Mexico.xml",
    "https://cdn.epg.guru/7dayiptv/UnitedStates.xml",
]

def arreglar_acentos(texto):
    if not texto:
        return texto
    try:
        if "Ã" in texto or "Â" in texto:
            for _ in range(2):
                try:
                    texto = texto.encode('latin1').decode('utf-8')
                except:
                    break
    except:
        pass
    return texto

headers = {"User-Agent": "Mozilla/5.0"}
tv = ET.Element("tv")
canales = {}
count = 0

for URL in URLS:
    print(f"Bajando {URL}...")
    r = requests.get(URL, timeout=180, headers=headers)
    raw = arreglar_acentos(r.content.decode('utf-8', errors='ignore'))

    # Si ya es XMLTV, lo fusionamos directo
    if "<tv" in raw.lower() and "<programme" in raw.lower():
        try:
            root = ET.fromstring(raw)
            for ch in root.findall("channel"):
                if ch.get("id") not in canales:
                    canales[ch.get("id")] = True
                    tv.append(ch)
            for pr in root.findall("programme"):
                tv.append(pr)
                count += 1
            print(f"-> {URL} XMLTV fusionado")
            continue
        except Exception as e:
            print(f"No se pudo parsear como XMLTV: {e}")

    # Parser Gracenote
    canales_local = {}
    for line in raw.splitlines()[:8000]:
        m = re.search(r'(\d{4,6})\s+\d{4,6}\s*$', line)
        if m:
            cid = m.group(1)
            nombre = arreglar_acentos(line[:m.start()].strip())
            if nombre and cid not in canales:
                canales[cid] = nombre
                ch = ET.SubElement(tv, "channel")
                ch.set("id", cid)
                ET.SubElement(ch, "display-name").text = nombre
                canales_local[cid] = True

    prog_pat = re.compile(r'(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})\s+(.+?)(?:https://|$)')
    for line in raw.splitlines():
        m = prog_pat.search(line)
        if not m:
            continue
        fecha, hora, resto = m.groups()
        titulo = arreglar_acentos(resto.split("  ")[0][:150].strip())
        if len(titulo) < 3:
            continue
        try:
            dt = datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M:%S")
            start = dt.strftime("%Y%m%d%H%M%S") + " +0000"
            stop = (dt + timedelta(minutes=90)).strftime("%Y%m%d%H%M%S") + " +0000"
            cid_match = re.search(r'\b(\d{4,6})\b', line[:100])
            cid = cid_match.group(1) if cid_match and cid_match.group(1) in canales else next(iter(canales_local), "62161")
            pr = ET.SubElement(tv, "programme")
            pr.set("start", start)
            pr.set("stop", stop)
            pr.set("channel", cid)
            t = ET.SubElement(pr, "title")
            t.set("lang", "es")
            t.text = titulo
            count += 1
        except:
            continue

# Guardar epg.xml y epg.xml.gz
xml_str = ET.tostring(tv, encoding="unicode")
pretty = minidom.parseString(xml_str).toprettyxml(indent="  ", encoding="UTF-8").decode("UTF-8")
open("epg.xml", "w", encoding="utf-8").write(pretty)

with open("epg.xml", 'rb') as f_in:
    with gzip.open("epg.xml.gz", 'wb', compresslevel=9) as f_out:
        f_out.writelines(f_in)

print(f"✓ epg.xml -> {len(canales)} canales, {count} programas")
print(f"✓ epg.xml.gz creado")
