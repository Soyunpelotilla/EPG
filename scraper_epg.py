#!/usr/bin/env python3
# ==============================================================================
# Script: scraper_epg.py
# Función: Raspa programación de gatotv.com y genera XML en formato XMLTV
# Zona horaria: España (UTC+1 invierno / UTC+2 verano), detectada automáticamente
# Nota: gatotv.com devuelve las horas ya en la zona horaria del visitante,
#       por lo que desde GitHub Actions (UTC) se reciben en UTC. Sin embargo,
#       al acceder con IP de España (geolocalización), la web devuelve hora
#       española directamente → no se necesita conversión.
# ==============================================================================

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
from xml.dom import minidom
import time
import re

# ==============================================================================
# ZONA HORARIA ESPAÑA - Detección automática
# Cambio de hora: último domingo de marzo (→ +0200) y octubre (→ +0100)
# ==============================================================================

def ultimo_domingo(year, month):
    """Devuelve la fecha del último domingo de un mes dado."""
    ultimo_dia = datetime(year, month + 1, 1) - timedelta(days=1) if month < 12 else datetime(year, 12, 31)
    dias_hasta_domingo = ultimo_dia.weekday() + 1  # weekday(): lunes=0, domingo=6
    if dias_hasta_domingo == 7:
        dias_hasta_domingo = 0
    return ultimo_dia - timedelta(days=dias_hasta_domingo)

def get_timezone_espana():
    """
    Devuelve el offset de España según la fecha actual.
    Verano (CEST): último domingo de marzo → último domingo de octubre → +0200
    Invierno (CET): resto del año → +0100
    """
