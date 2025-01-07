import os
import pdfplumber
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta
import locale


# Función para extraer datos desde el archivo PDF
def extract_data_from_pdf(pdf_path):
    memorandos = []  # Tabla 1
    activos_por_zona = {f"Zona{i}": [] for i in range(1, 10)}  # Diccionario para activos por zona
    memorandos_vistos = set()  # Conjunto para evitar memorandos repetidos
    zona_limits = {
        "Zona1": 5, "Zona2": 3, "Zona3": 4, "Zona4": 5,
        "Zona5": 8, "Zona6": 4, "Zona7": 5, "Zona8": 3, "Zona9": 3
    }

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            memorando, fecha_envio = extract_memorando(text)

            if memorando in memorandos_vistos:
                continue  # Ignorar memorandos ya procesados

            zona = determine_zone(memorando)
            tables = page.extract_tables()

            for table in tables:
                for row in table:
                    if len(row) >= 2 and row[1] and row[1].strip():
                        if row[0] == 'TOTAL':
                            continue
                        cleaned_value = re.sub(r'\.', '', row[1].strip())
                        if cleaned_value.isdigit():
                            activos = int(cleaned_value)
                            if zona and len(activos_por_zona[zona]) < zona_limits[zona]:
                                activos_por_zona[zona].append(activos)

            if memorando:
                zona = determine_zone(memorando)
                coordinacion_zonal = get_zonal_number(zona)
                memorandos.append({
                    "COORDINACIÓN ZONAL": coordinacion_zonal,
                    "NRO. MEMORANDO": memorando,
                    "FECHA ENVÍO MEMORANDO": fecha_envio
                })
                memorandos_vistos.add(memorando)

    return memorandos, activos_por_zona

# Función para obtener el número de zona
def determine_zone(memorando):
    zonas_map = {
        "CZ-1": "Zona1", "CZ-2": "Zona2", "CZ-3": "Zona3",
        "CZ-4": "Zona4", "CZ-5": "Zona5", "CZ-6": "Zona6",
        "CZ-7": "Zona7", "CZ-8": "Zona8", "DCDMQ": "Zona9"
    }
    for key, zona in zonas_map.items():
        if key in memorando:
            return zona
    return None

# Función para obtener el número de la zona
def get_zonal_number(zona):
    zonal_map = {
        "Zona1": 1, "Zona2": 2, "Zona3": 3, "Zona4": 4,
        "Zona5": 5, "Zona6": 6, "Zona7": 7, "Zona8": 8, "Zona9": 9
    }
    return zonal_map.get(zona)

locale.setlocale(locale.LC_TIME, 'C')  # Configuración por defecto compatible

# Función para calcular el mes y año siguiente
def get_next_month_year():
    current_date = datetime.now()
    next_month = current_date + relativedelta(months=1)
    month_name = next_month.strftime('%B').upper()
    year = next_month.year
    return month_name, year

# Función para extraer memorando y fecha
def extract_memorando(text):
    match = re.search(r"Memorando Nro\. MIES-[^\s]+", text)
    fecha_envio = None

    if match:
        memorando = match.group(0)

        if "MIES-SATP-DCDMQ" in memorando:
            fecha_match = re.search(r"(\d{1,2}\s+de\s+[a-záéíóúñ]+)", text, re.IGNORECASE)
        else:
            fecha_match = re.search(r"(\d{1,2}\s+de\s+[a-záéíóúñ]+)", text, re.IGNORECASE)

        if fecha_match:
            fecha_envio = fecha_match.group(1).strip().upper()
        else:
            fecha_envio = "FECHA NO ENCONTRADA"

        return memorando, fecha_envio
    return None, None
