from flask import Flask, request, render_template, send_file, session, redirect, url_for
import os
import pandas as pd
import hashlib
from werkzeug.utils import secure_filename
from utils import extract_data_from_pdf, get_next_month_year, determine_zone

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = '/tmp/uploads'
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}  
app.config['PROCESSED_FOLDER'] = '/tmp/processed'
app.secret_key = 'supersecretkey'  # Necesario para el uso de session
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['PROCESSED_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def generate_file_hash(filepath):
    """Genera un hash SHA256 para el archivo dado."""
    hash_sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(4096):
            hash_sha256.update(chunk)
    return hash_sha256.hexdigest()

@app.route("/", methods=["GET"])
def index():
    session.clear()
    session['all_memorandos'] = []
    session['activos_por_zona_global'] = {f"Zona{i}": [] for i in range(1, 10)}
    session['uploaded_files'] = 0
    session['uploaded_files_list'] = []  # Para almacenar los nombres de los archivos cargados
    session['uploaded_file_hashes'] = []  # Para almacenar los hashes de los archivos cargados
    return render_template("index.html")

@app.route("/consolidado", methods=["GET", "POST"])
def consolidado():      
    if request.method == "POST":
        files = request.files.getlist("pdf_files")

        if not files:
            return render_template("consolidado.html", error_message="No se han cargado archivos.")

        for file in files:
            filename = secure_filename(file.filename)
            if not filename.lower().endswith('.pdf'):
                return render_template("consolidado.html", error_message="Solo se permiten archivos PDF.")
            
            #Verificar si el archivo ya ha sido cargado previamente por nombre
            if filename in session.get('uploaded_files_list', []):
                return render_template("consolidado.html", error_message=f"El archivo '{filename}' ya ha sido cargado previamente.")

            # Verificar si el archivo ya ha sido cargado por hash
            pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(pdf_path)

            file_hash = generate_file_hash(pdf_path)
            if file_hash in session.get('uploaded_file_hashes', []):
                return render_template("consolidado.html", error_message=f"El archivo '{filename}' ya ha sido cargado previamente.")

            # Guardar el nombre del archivo y su hash en la sesión
            session['uploaded_files_list'].append(filename)
            session['uploaded_file_hashes'].append(file_hash)

            # Validar si el archivo PDF se puede procesar
            try:
                # Extrae datos del PDF
                memorandos, activos_por_zona = extract_data_from_pdf(pdf_path)
                if memorandos is None or activos_por_zona is None:
                    return render_template("consolidado.html", error_message="El archivo PDF no tiene el formato correcto.")
            
                session['uploaded_files'] += 1
                session['all_memorandos'].extend(memorandos)

                # Consolidar activos por zona
                for zona, activos in activos_por_zona.items():
                    session['activos_por_zona_global'][zona].extend(activos)

            except Exception as e:
                # Captura cualquier error que pueda ocurrir durante el procesamiento
                return render_template("consolidado.html", error_message="Ocurrió un error al procesar el archivo PDF: " + str(e))

        if session['uploaded_files'] >= 9:
            return generate_excel()
        else:
            return render_template("consolidado.html", message=f"PDF cargado exitosamente. PDFs cargados: {session['uploaded_files']}/9")    
    
    # Agregar un retorno por si se accede a la ruta con un método GET
    return render_template("consolidado.html")

def generate_excel():
    zona_totals = {zona: sum(activos) for zona, activos in session['activos_por_zona_global'].items()}
    
    # Añadir una tercera columna con los totales según la zona
    for memorando in session['all_memorandos']:
        zona = determine_zone(memorando["NRO. MEMORANDO"])
        memorando["TOTAL USUARIOS APROBADOS POR UNIDAD DESCONCENTRADA"] = zona_totals.get(zona, 0)

    # Obtener el nombre del mes y el año para el título dinámico
    month_name, year = get_next_month_year()
    table1_title = f"CONSOLIDADO DE PAGO BONO \"{month_name} {year}\""
    table2_title = "RESUMEN"

    if session['all_memorandos']:
        excel_path = os.path.join(app.config['PROCESSED_FOLDER'], "resultados.xlsx")
        with pd.ExcelWriter(excel_path, engine="xlsxwriter") as writer:
            # Escribir tabla 1 (con la nueva columna) y título
            df_memorandos = pd.DataFrame(session['all_memorandos'])

             # Ordenar el DataFrame por la columna "COORDINACIÓN ZONAL" (de menor a mayor)
            df_memorandos = df_memorandos.sort_values(by="COORDINACIÓN ZONAL", ascending=True)

            # Obtener el total general para la nueva columna
            total_usuarios_aprobados = df_memorandos["TOTAL USUARIOS APROBADOS POR UNIDAD DESCONCENTRADA"].sum()
            
            total_row = {
                "COORDINACIÓN ZONAL": "TOTAL",
                "NRO. MEMORANDO": "",
                "FECHA ENVÍO MEMORANDO": "",
                "TOTAL USUARIOS APROBADOS POR UNIDAD DESCONCENTRADA": total_usuarios_aprobados
            }
            df_memorandos = pd.concat([df_memorandos, pd.DataFrame([total_row])], ignore_index=True)

            df_memorandos.to_excel(writer, sheet_name="Resumen", index=False, startrow=1)

            workbook  = writer.book
            worksheet = writer.sheets["Resumen"]
            num_rows_memorandos = len(df_memorandos) + 1
            num_cols_memorandos = len(df_memorandos.columns)
            # Agregar el título dinámico de la Tabla 1 y centrarlo
            worksheet.merge_range(0, 0, 0, num_cols_memorandos - 1, table1_title, workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center', 'valign': 'vcenter'}))

            worksheet.add_table(1, 0, num_rows_memorandos, num_cols_memorandos - 1, 
                                {'columns': [{'header': col} for col in df_memorandos.columns]})

            # Ajustar el ancho de las columnas de la Tabla 1 para que se ajusten a su contenido
            for i, col in enumerate(df_memorandos.columns):
                max_length = max(df_memorandos[col].astype(str).apply(len).max(), len(col))  # Longitud máxima de la columna
                worksheet.set_column(i, i, max_length + 2)  # Añadir un poco de espacio extra

            # Crear DataFrame de activos
            df_activos = pd.DataFrame(dict([(k, pd.Series(v)) for k, v in session['activos_por_zona_global'].items()]))
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
            startrow_activos = len(df_memorandos) + 3
            startcol_activos = 4 # Columna 'E', que corresponde al índice 4
            
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

    # Reiniciar la sesión para una nueva carga
    session.clear()
    session['uploaded_files'] = 0
    session['uploaded_files_list'] = []
    session['uploaded_file_hashes'] = []
    session['all_memorandos'] = []
    session['activos_por_zona_global'] = {f"Zona{i}": [] for i in range(1, 10)} 
    return send_file(excel_path, as_attachment=True)

@app.route("/documentacion")
def documentacion():
    return render_template("documentacion.html")

@app.route("/contacto")
def contacto():
    return render_template("contacto.html")

if __name__ == "__main__":
    #app.run(host='0.0.0.0', port=10000)
    app.run(debug=True)