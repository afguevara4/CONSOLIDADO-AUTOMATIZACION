from flask import Flask, request, render_template, send_file
import os
import pandas as pd
from werkzeug.utils import secure_filename
from utils import extract_data_from_pdf, get_next_month_year, determine_zone

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = '/path/to/upload/folder'
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}  
app.config['PROCESSED_FOLDER'] = 'processed'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['PROCESSED_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/consolidado", methods=["GET", "POST"])
def consolidado():      
    if request.method == "POST":
        files = request.files.getlist("pdf_files")
        all_memorandos = []  # Tabla 1
        activos_por_zona_global = {f"Zona{i}": [] for i in range(1, 10)}  # Tabla 2

        for file in files:
            filename = secure_filename(file.filename)
            if not filename.lower().endswith('.pdf'):
                return render_template("consolidado.html", error_message="Solo se permiten archivos PDF.")
            
            pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(pdf_path)

            # Validar si el archivo PDF se puede procesar
            try:
                # Extrae datos del PDF
                memorandos, activos_por_zona = extract_data_from_pdf(pdf_path)
                if memorandos is None or activos_por_zona is None:
                    return render_template("consolidado.html", error_message="El archivo PDF no tiene el formato correcto.")
            
                all_memorandos.extend(memorandos)

                # Consolidar activos por zona
                for zona, activos in activos_por_zona.items():
                    activos_por_zona_global[zona].extend(activos)

            except Exception as e:
                # Captura cualquier error que pueda ocurrir durante el procesamiento
                return render_template("consolidado.html", error_message="Ocurrió un error al procesar el archivo PDF: " + str(e))

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

                #print(df_memorandos)

                # Obtener el total general para la nueva columna
                total_usuarios_aprobados = df_memorandos["TOTAL USUARIOS APROBADOS POR UNIDAD DESCONCENTRADA"].sum()

                # Añadir la fila TOTAL al DataFrame
                total_row = {
                    "COORDINACIÓN ZONAL": "TOTAL",  # Texto para la primera columna
                    "NRO. MEMORANDO": "",
                    "FECHA ENVÍO MEMORANDO": "",
                    "TOTAL USUARIOS APROBADOS POR UNIDAD DESCONCENTRADA": total_usuarios_aprobados
                }
                df_memorandos = pd.concat([df_memorandos, pd.DataFrame([total_row])], ignore_index=True)

                df_memorandos.to_excel(writer, sheet_name="Resumen", index=False, startrow=1) 

                # Obtener el número de filas y columnas de df_memorandos
                num_rows_memorandos = len(df_memorandos) + 1
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
                #df_activos = df_activos.fillna(0)

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

    return render_template("consolidado.html")

@app.route("/documentacion")
def documentacion():
    return render_template("documentacion.html")

@app.route("/contacto")
def contacto():
    return render_template("contacto.html")

if __name__ == "__main__":
     app.run(host='0.0.0.0', port=10000)