import requests
import re
import gzip
import os
import xml.etree.ElementTree as ET

URLS = [
    "https://cdn.epg.guru/7dayiptv/Mexico.xml",
    "https://cdn.epg.guru/7dayiptv/UnitedStates.xml",
]

def arreglar_acentos(texto):
    if not texto:
        return texto
    if "Ã" in texto or "Â" in texto:
        try:
            texto = texto.encode('latin1').decode('utf-8')
        except:
            pass
    return texto

headers = {"User-Agent": "Mozilla/5.0"}
seen_channels = set()
total_prog = 0

print("Creando epg.xml en modo streaming...")
with open("epg.xml", "w", encoding="utf-8") as out:
    out.write('<?xml version="1.0" encoding="UTF-8"?>\n<tv>\n')

    for URL in URLS:
        print(f"Bajando {URL}...")
        # Bajamos a archivo temporal para no tenerlo en RAM
        tmp_file = "temp_epg.xml"
        with requests.get(URL, headers=headers, stream=True, timeout=300) as r:
            r.raise_for_status()
            with open(tmp_file, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024*1024):
                    f.write(chunk)
        
        print(f"Procesando {URL}...")
        # iterparse = no carga todo, va leyendo poco a poco
        try:
            context = ET.iterparse(tmp_file, events=("end",))
            for event, elem in context:
                if elem.tag == "channel":
                    cid = elem.get("id")
                    if cid not in seen_channels:
                        seen_channels.add(cid)
                        # arreglar acentos en display-name
                        for dn in elem.findall("display-name"):
                            if dn.text:
                                dn.text = arreglar_acentos(dn.text)
                        out.write(ET.tostring(elem, encoding="unicode"))
                        out.write("\n")
                    elem.clear()
                elif elem.tag == "programme":
                    # arreglar titulo
                    title = elem.find("title")
                    if title is not None and title.text:
                        title.text = arreglar_acentos(title.text)
                    out.write(ET.tostring(elem, encoding="unicode"))
                    out.write("\n")
                    total_prog += 1
                    elem.clear()
            print(f"-> {URL} OK")
        except Exception as e:
            print(f"Error procesando {URL}: {e}")
            # fallback: si falla iterparse, intentamos copiar tal cual
            continue
        finally:
            if os.path.exists(tmp_file):
                os.remove(tmp_file)

    out.write('</tv>\n')

print(f"Total: {len(seen_channels)} canales, {total_prog} programas")

# Crear gz
print("Comprimiendo a epg.xml.gz...")
with open("epg.xml", 'rb') as f_in:
    with gzip.open("epg.xml.gz", 'wb', compresslevel=9) as f_out:
        while True:
            chunk = f_in.read(1024*1024)
            if not chunk:
                break
            f_out.write(chunk)

print(f"✓ epg.xml ({os.path.getsize('epg.xml')/1024/1024:.2f} MB)")
print(f"✓ epg.xml.gz ({os.path.getsize('epg.xml.gz')/1024/1024:.2f} MB)")
