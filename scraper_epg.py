import requests, re
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime, timedelta

URL = "https://cdn.epg.guru/7dayiptv/Mexico.xml"

def arreglar_acentos(texto):
    if not texto:
        return texto
    try:
        # Arregla siÃ³n -> sión, Ã¡ -> á, etc. (2 pasadas por si viene triple)
        if "Ã" in texto or "Â" in texto:
            for _ in range(2):
                try:
                    texto = texto.encode('latin1').decode('utf-8')
                except:
                    break
    except:
        pass
    return texto

print(f"Bajando {URL}...")
headers = {"User-Agent":"Mozilla/5.0"}
r = requests.get(URL, timeout=120, headers=headers)
try:
    raw = r.content.decode('utf-8')
except:
    raw = r.content.decode('latin1')

tv = ET.Element("tv")

# Si ya es XMLTV, lo guardamos directo pero arreglando acentos
if "<tv" in raw.lower() and "<programme" in raw.lower():
    raw = arreglar_acentos(raw)
    open("guide.xml","w",encoding="utf-8").write(raw)
    print("Ya era XMLTV con acentos arreglados")
    exit()

# Si no, es el formato de tus capturas (Gracenote)
canales = {}
for line in raw.splitlines()[:5000]:
    m = re.search(r'(\d{4,6})\s+\d{4,6}\s*$', line)
    if m:
        cid = m.group(1)
        nombre = arreglar_acentos(line[:m.start()].strip())
        if nombre and cid not in canales:
            canales[cid] = nombre
            ch = ET.SubElement(tv,"channel")
            ch.set("id", cid)
            ET.SubElement(ch,"display-name").text = nombre

print(f"{len(canales)} canales")

prog_pat = re.compile(r'(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})\s+(.+?)(?:https://|$)')
count=0
for line in raw.splitlines():
    m = prog_pat.search(line)
    if not m: continue
    fecha, hora, resto = m.groups()
    titulo = arreglar_acentos(resto.split("  ")[0][:120].strip())
    if len(titulo) < 3: continue
    try:
        dt = datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M:%S")
        start = dt.strftime("%Y%m%d%H%M%S") + " +0000"
        stop = (dt + timedelta(minutes=60)).strftime("%Y%m%d%H%M%S") + " +0000"
        cid_match = re.search(r'\b(\d{4,6})\b', line[:100])
        cid = cid_match.group(1) if cid_match and cid_match.group(1) in canales else "62161"
        if cid not in canales:
            canales[cid]="FOX MX"
            ch=ET.SubElement(tv,"channel")
            ch.set("id",cid)
            ET.SubElement(ch,"display-name").text="FOX MX"
        pr = ET.SubElement(tv,"programme")
        pr.set("start", start)
        pr.set("stop", stop)
        pr.set("channel", cid)
        t = ET.SubElement(pr,"title")
        t.set("lang","es")
        t.text = titulo
        count+=1
    except:
        continue

xml_str = ET.tostring(tv, encoding="unicode")
pretty = minidom.parseString(xml_str).toprettyxml(indent="  ", encoding="UTF-8").decode("UTF-8")
open("guide.xml","w",encoding="utf-8").write(pretty)
print(f"✓ guide.xml {count} programas con acentos arreglados")
