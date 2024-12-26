from flask import Flask, request, render_template, send_file
import os
import pandas as pd
import pdfplumber
import re
from werkzeug.utils import secure_filename
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta
import locale

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['PROCESSED_FOLDER'] = 'processed'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['PROCESSED_FOLDER'], exist_ok=True)

def extract_data_from_pdf(pdf_path):
    memorandos = []  # Tabla 1
    activos_por_zona = {f"Zona{i}": [] for i in range(1, 10)}  # Diccionario para activos por zona
    memorandos_vistos = set()  # Conjunto para evitar memorandos repetidos
    zona_limits = {
        "Zona1": 5,  # Por ejemplo, 5 datos para Zona1
        "Zona2": 3,
        "Zona3": 4,
        "Zona4": 5,
        "Zona5": 8,  # 8 datos para Zona5
        "Zona6": 4,
        "Zona7": 5,
        "Zona8": 3,  # 3 datos para Zona8
        "Zona9": 3
    }

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            memorando, fecha_envio = extract_memorando(text)  # Extraer número de memorando y la fecha de envío

            if memorando in memorandos_vistos:
                continue  # Ignorar memorandos ya procesados

            zona = determine_zone(memorando)  # Determinar la zona con base en el memorando
            print(f"Memorando: {memorando}, Zona: {zona}")  # Depuración para verificar la zona asignada
            tables = page.extract_tables()

            for table in tables:
                for row in table:
                    # Ignorar filas con la palabra 'TOTAL' y asegurar que la fila tenga al menos dos columnas
                    if len(row) >= 2 and row[1] and row[1].strip():
                        # Verificar si la fila es la de 'TOTAL'
                        if row[0] == 'TOTAL':
                            continue  # Omite la fila que contiene 'TOTAL'

                        # Limpiar el valor numérico eliminando los puntos
                        cleaned_value = re.sub(r'\.', '', row[1].strip())  # Eliminar puntos

                        # Verificar si el valor es un número antes de convertirlo
                        if cleaned_value.isdigit():
                            activos = int(cleaned_value)
                            if zona:
                                # Verificar si se ha superado el límite de datos para esta zona
                                if len(activos_por_zona[zona]) < zona_limits[zona]:
                                    print(f"Zona {zona}: Activo: {activos}")  # Imprime los valores de otras zonas
                                    activos_por_zona[zona].append(activos)
                                else:
                                    print(f"Zona {zona} ha alcanzado el límite de {zona_limits[zona]} datos. Ignorando el dato: {activos}")

            # Registrar memorando en la tabla 1
            if memorando:
                # Añadir la fecha de envío al memorando
                memorandos.append({"NRO. MEMORANDO": memorando, "FECHA ENVÍO MEMORANDO": fecha_envio})
                memorandos_vistos.add(memorando)  # Marcar el memorando como procesado

    return memorandos, activos_por_zona

# Función para determinar la zona según el memorando (sin cambios)
def determine_zone(memorando):
    zonas_map = {
        "CZ-1": "Zona1", "CZ-2": "Zona2", "CZ-3": "Zona3",
        "CZ-4": "Zona4", "CZ-5": "Zona5", "CZ-6": "Zona6",
        "CZ-7": "Zona7", "CZ-8": "Zona8", "DCDMQ": "Zona9"  # Asegúrate que DCDMQ esté correctamente mapeado
    }
    for key, zona in zonas_map.items():
        if key in memorando:
            return zona
    return None

# Configurar el idioma en español
locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')

# Función para calcular el mes y año siguiente en español
def get_next_month_year():
    current_date = datetime.now()
    next_month = current_date + relativedelta(months=1)
    month_name = next_month.strftime('%B').upper()  # Obtener el nombre del mes en español
    year = next_month.year
    return month_name, year

def extract_memorando(text):
    # Buscar el número del memorando
    match = re.search(r"Memorando Nro\. MIES-[^\s]+", text)  # Regex para encabezados de memorandos
    fecha_envio = None

    if match:
        memorando = match.group(0)

        # Verificar si el memorando contiene "DCDMQ"
        if "MIES-SATP-DCDMQ" in memorando:
            # Ajustar el patrón para encontrar la fecha en el formato "13 de diciembre"
            fecha_match = re.search(r"(\d{1,2}\s+de\s+[a-záéíóúñ]+)", text, re.IGNORECASE)
        else:
            # Para el resto de zonas, el formato de la fecha sigue siendo estándar
            fecha_match = re.search(r"(\d{1,2}\s+de\s+[a-záéíóúñ]+)", text, re.IGNORECASE)

        if fecha_match:
            # Extraer solo el día y el mes
            fecha_envio = fecha_match.group(1).strip().upper()  # Convertir a mayúsculas
        else:
            fecha_envio = "FECHA NO ENCONTRADA"  # Valor por defecto si no se encuentra la fecha

        return memorando, fecha_envio
    return None, None

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        files = request.files.getlist("pdf_files")
        all_memorandos = []  # Tabla 1
        activos_por_zona_global = {f"Zona{i}": [] for i in range(1, 10)}  # Tabla 2

        for file in files:
            filename = secure_filename(file.filename)
            pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(pdf_path)
            memorandos, activos_por_zona = extract_data_from_pdf(pdf_path)
            all_memorandos.extend(memorandos)

            # Consolidar activos por zona
            for zona, activos in activos_por_zona.items():
                activos_por_zona_global[zona].extend(activos)

        # Calcular totales por zona
        zona_totals = {zona: sum(activos) for zona, activos in activos_por_zona_global.items()}

        # Añadir una tercera columna con los totales según la zona
        for memorando in all_memorandos:
            zona = determine_zone(memorando["NRO. MEMORANDO"])
            memorando["TOTAL USUARIOS APROBADOS POR UNIDAD DESCONCENTRADA"] = zona_totals.get(zona, 0)  # Agregar el total correspondiente a la zona

        # Obtener el nombre del mes y el año para el título dinámico
        month_name, year = get_next_month_year()
        table1_title = f"CONSOLIDADO DE PAGO BONO \"{month_name} {year}\""
        table2_title = "RESUMEN"

        # Crear archivo Excel respetando la tabla 1
        if all_memorandos:
            excel_path = os.path.join(app.config['PROCESSED_FOLDER'], "resultados.xlsx")
            with pd.ExcelWriter(excel_path, engine="xlsxwriter") as writer:
                # Escribir tabla 1 (con la nueva columna) y título
                df_memorandos = pd.DataFrame(all_memorandos)
                df_memorandos.to_excel(writer, sheet_name="Resumen", index=False, startrow=1)

                print(df_memorandos)

                # Obtener el número de filas y columnas de df_memorandos
                num_rows_memorandos = len(df_memorandos)
                num_cols_memorandos = len(df_memorandos.columns)

                # Aplicar formato de tabla en "Resumen" para la Tabla 1
                workbook  = writer.book
                worksheet = writer.sheets["Resumen"]
                
                # Agregar el título dinámico de la Tabla 1 y centrarlo
                worksheet.merge_range(0, 0, 0, num_cols_memorandos - 1, table1_title, workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center', 'valign': 'vcenter'}))

                worksheet.add_table(1, 0, num_rows_memorandos, num_cols_memorandos - 1, 
                                    {'columns': [{'header': col} for col in df_memorandos.columns]})

                # Ajustar el ancho de las columnas de la Tabla 1 para que se ajusten a su contenido
                for i, col in enumerate(df_memorandos.columns):
                    max_length = max(df_memorandos[col].astype(str).apply(len).max(), len(col))  # Longitud máxima de la columna
                    worksheet.set_column(i, i, max_length + 2)  # Añadir un poco de espacio extra

                # Crear DataFrame de activos
                df_activos = pd.DataFrame(dict([(k, pd.Series(v)) for k, v in activos_por_zona_global.items()]))

                # Completar valores faltantes en las celdas vacías para evitar problemas al sumar
                df_activos = df_activos.fillna(0)

                # Calcular la fila de totales por zona
                totals_row = df_activos.sum(axis=0, skipna=True)

                # Añadir la fila de totales al DataFrame
                totals_row.name = "TOTAL"
                df_activos = pd.concat([df_activos, totals_row.to_frame().T])

                # Eliminar el índice para evitar que se exporte
                df_activos.reset_index(drop=True, inplace=True)

                # Obtener el número de filas y columnas de df_activos
                num_rows_activos = len(df_activos)
                num_cols_activos = len(df_activos.columns)

                # Determinar la fila de inicio para escribir la Tabla 2
                startrow_activos = num_rows_memorandos + 3
                startcol_activos = 4  # Columna 'E', que corresponde al índice 4

                # Escribir DataFrame en el archivo Excel
                df_activos.to_excel(writer, sheet_name="Resumen", index=False, 
                                    startrow=startrow_activos, startcol=startcol_activos)

                # Agregar formato de tabla en Excel
                worksheet.add_table(
                    startrow_activos, startcol_activos,
                    startrow_activos + num_rows_activos - 1, startcol_activos + num_cols_activos - 1, 
                    {
                        'columns': [{'header': col} for col in df_activos.columns],
                        'name': 'TablaActivos'  # Nombre opcional para identificar la tabla
                    }
                )

                # Agregar el título "RESUMEN" y centrarlo
                worksheet.merge_range(startrow_activos - 1, startcol_activos, 
                                      startrow_activos - 1, startcol_activos + num_cols_activos - 1, 
                                      table2_title, workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center', 'valign': 'vcenter'}))

                # Ajustar el ancho de las columnas de la Tabla 2 para que se ajusten a su contenido
                for i in range(startcol_activos, startcol_activos + num_cols_activos):
                    worksheet.set_column(i, i, 15)

                # Ajustar el ancho de las columnas de la Tabla 1 para que el título se ajuste al contenido
                worksheet.set_column(0, num_cols_memorandos - 1, 15)

                # Establecer el ajuste de texto en las celdas para que el texto se ajuste correctamente
                cell_format = workbook.add_format({'text_wrap': True, 'valign': 'top'})
                worksheet.set_column(0, num_cols_memorandos - 1, 20, cell_format)  # Ajustar la columna 0 hasta la última columna de la Tabla 1
                worksheet.set_column(startcol_activos, startcol_activos + num_cols_activos - 1, 20, cell_format)  # Ajustar la columna 0 hasta la última columna de la Tabla 2

            return send_file(excel_path, as_attachment=True)

    return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=True)