from flask import Flask, request, render_template, send_file
import os
import pandas as pd
from werkzeug.utils import secure_filename
from utils import extract_data_from_pdf, get_next_month_year, determine_zone

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = '/tmp/uploads'
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}  
app.config['PROCESSED_FOLDER'] = '/tmp/processed'
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

            try:
                memorandos, activos_por_zona = extract_data_from_pdf(pdf_path)
                if memorandos is None or activos_por_zona is None:
                    return render_template("consolidado.html", error_message="El archivo PDF no tiene el formato correcto.")
                
                all_memorandos.extend(memorandos)

                for zona, activos in activos_por_zona.items():
                    activos_por_zona_global[zona].extend(activos)

            except Exception as e:
                return render_template("consolidado.html", error_message="Ocurrió un error al procesar el archivo PDF: " + str(e))

        zona_totals = {zona: sum(activos) for zona, activos in activos_por_zona_global.items()}

        for memorando in all_memorandos:
            zona = determine_zone(memorando["NRO. MEMORANDO"])
            memorando["TOTAL USUARIOS APROBADOS POR UNIDAD DESCONCENTRADA"] = zona_totals.get(zona, 0)

        month_name, year = get_next_month_year()
        table1_title = f"CONSOLIDADO DE PAGO BONO \"{month_name} {year}\""
        table2_title = "RESUMEN"

        if all_memorandos:
            excel_path = os.path.join(app.config['PROCESSED_FOLDER'], "resultados.xlsx")
            with pd.ExcelWriter(excel_path, engine="xlsxwriter") as writer:
                df_memorandos = pd.DataFrame(all_memorandos)
                df_memorandos.to_excel(writer, sheet_name="Resumen", index=False, startrow=1)

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
